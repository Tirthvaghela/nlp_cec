"""Pilot server launcher (security audit V1). Use this instead of plain `uvicorn` for the classroom pilot.

    python -m scripts.run_server --host 0.0.0.0 --port 8000 --ssl-certfile cert.pem --ssl-keyfile key.pem

Why: plain `uvicorn app.main:app` enables proxy-header processing by default and trusts X-Forwarded-For from
127.0.0.1. Any request that reaches the server through a local process (a reverse proxy, the Vite dev server, any
other program on the host) could then choose its own client address and step around the per-IP rate limits.

This launcher:
* turns proxy-header processing OFF when TRUSTED_PROXIES is empty (the supported pilot topology: browsers talk to
  this server directly, so the TCP peer IS the client);
* when TRUSTED_PROXIES is set, trusts exactly those addresses - never uvicorn's implicit 127.0.0.1 default - and
  refuses loopback/wildcard entries in PILOT_MODE (app.config.trusted_proxy_problems);
* runs exactly ONE process (the rate-limit counters live in process memory);
* marks the process so a PILOT_MODE server refuses to start without the launcher, and /api/health reports the
  client-address mode for the preflight;
* (V12) in PILOT_MODE refuses to serve beyond loopback without TLS: either this server terminates TLS (--ssl-certfile
  and --ssl-keyfile, both readable), or TLS_TERMINATED_BY_PROXY=true states that the IT-approved proxy in
  TRUSTED_PROXIES does. Certificates and proxy addresses are supplied by IT - never generated or assumed here;
* (V7) in PILOT_MODE sets HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE so the model is loaded only from the local cache
  that the preflight hashed, never silently updated to a newer revision at start-up (scoring code is unchanged);
* (sprint 5, A4) in PILOT_MODE refuses to start when SENTENCE_TRANSFORMERS_HOME, TRANSFORMERS_CACHE or a similar
  variable, or a local directory named like the model, could make the libraries load files other than the hub cache
  (app/model_cache.py).
"""

from __future__ import annotations

import argparse
import ipaddress
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LAUNCHER_ENV, ADDRESS_MODE_ENV = "ANSWERWISE_LAUNCHER", "ANSWERWISE_CLIENT_ADDRESS_MODE"
TRANSPORT_ENV = "ANSWERWISE_TRANSPORT"


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def transport_mode(settings, host: str, ssl_certfile: str | None, ssl_keyfile: str | None) -> str:
    """tls-direct | tls-proxy | loopback-plain | plain. Raises SystemExit for an unsafe pilot transport (V12)."""
    if ssl_certfile or ssl_keyfile:
        missing = [f for f in (ssl_certfile, ssl_keyfile) if not f or not Path(f).is_file()]
        if missing:
            sys.exit("Refusing to start: TLS needs BOTH --ssl-certfile and --ssl-keyfile as readable files.")
        return "tls-direct"
    if settings.tls_terminated_by_proxy:
        if not settings.trusted_proxy_list:
            sys.exit("Refusing to start: TLS_TERMINATED_BY_PROXY=true needs the proxy address in TRUSTED_PROXIES.")
        return "tls-proxy"
    if _is_loopback(host):
        return "loopback-plain"
    if settings.pilot_mode:
        sys.exit("Refusing to start: PILOT_MODE serves beyond this machine, so TLS is required - pass --ssl-certfile and "
                 "--ssl-keyfile (IT-issued certificate), or set TLS_TERMINATED_BY_PROXY=true with the IT-approved proxy "
                 "in TRUSTED_PROXIES. Passwords and login tokens must not cross the network in clear text.")
    return "plain"


def build_config(settings, host: str, port: int, ssl_certfile: str | None = None, ssl_keyfile: str | None = None,
                 app="app.main:app"):
    """uvicorn.Config for the pilot. Raises SystemExit on an unsafe proxy configuration."""
    import uvicorn

    from app.config import trusted_proxy_problems

    proxies = settings.trusted_proxy_list
    problems = trusted_proxy_problems(proxies, pilot=settings.pilot_mode)
    if problems:
        sys.exit("Refusing to start: " + "; ".join(problems))
    transport = transport_mode(settings, host, ssl_certfile, ssl_keyfile)
    if settings.pilot_mode:
        from app import model_cache

        if (cache := model_cache.cache_problems(settings.embedding_model, workdirs=(Path.cwd(),))):
            sys.exit("Refusing to start: the model could be loaded from somewhere the preflight does not hash: "
                     + "; ".join(cache))
    os.environ[LAUNCHER_ENV] = "1"
    os.environ[ADDRESS_MODE_ENV] = "trusted_proxies" if proxies else "direct"
    os.environ[TRANSPORT_ENV] = transport
    if settings.pilot_mode:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    return uvicorn.Config(
        app, host=host, port=port, workers=1, log_config=None,
        proxy_headers=bool(proxies),
        forwarded_allow_ips=proxies if proxies else [],  # explicit: never uvicorn's implicit 127.0.0.1
        ssl_certfile=ssl_certfile, ssl_keyfile=ssl_keyfile,
    )


def main(argv=None) -> None:
    import uvicorn

    from app.config import get_settings

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--ssl-certfile")
    ap.add_argument("--ssl-keyfile")
    args = ap.parse_args(argv)
    settings = get_settings()  # PILOT_MODE: refuses an unsafe configuration here already
    config = build_config(settings, args.host, args.port, args.ssl_certfile, args.ssl_keyfile)
    if os.environ[TRANSPORT_ENV] == "plain":
        print("WARNING: serving beyond this machine without TLS - passwords and tokens travel in clear text. The pilot "
              "requires TLS (docs/PILOT_RUNBOOK.md, V12).", file=sys.stderr)
    print(f"transport: {os.environ[TRANSPORT_ENV]}; client-address mode: {os.environ[ADDRESS_MODE_ENV]} (proxy headers {'ON for ' + str(config.forwarded_allow_ips) if config.proxy_headers else 'OFF'}), 1 process")
    uvicorn.Server(config).run()


if __name__ == "__main__":
    main()

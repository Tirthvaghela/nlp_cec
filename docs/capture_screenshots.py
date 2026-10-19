"""Capture README screenshots of the running app (read-only: it only signs in and views pages).

Prerequisites: backend on :8000 and frontend dev server on :5173 with seed data loaded.
    pip install playwright==1.55.0          # uses the locally installed Microsoft Edge
    python docs/capture_screenshots.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:5173"
OUT = Path(__file__).resolve().parent / "screenshots"
OUT.mkdir(exist_ok=True)
errors: list[str] = []


def login(page, email, password):
    page.goto(f"{BASE}/login")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password", exact=True).fill(password)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url(re.compile(r"/(teacher|student)$"))


def shot(page, name, full=True):
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(400)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
    print("saved", name)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page = ctx.new_page()
        page.on("console", lambda m: m.type == "error" and errors.append(f"{page.url}: {m.text}"))
        page.on("pageerror", lambda e: errors.append(f"{page.url}: {e}"))

        page.goto(f"{BASE}/login")
        shot(page, "01-login", full=False)

        login(page, "teacher@answerwise.dev", "Teacher@123")
        shot(page, "02-teacher-dashboard")
        page.goto(f"{BASE}/teacher/assessments")
        shot(page, "03-assessments")
        page.get_by_role("link", name="NLP Unit 2: Text Preprocessing").click()
        page.wait_for_url(re.compile(r"/teacher/assessments/\w+$"))
        shot(page, "04-assessment-questions")
        page.get_by_role("tab", name=re.compile("Submissions")).click()
        shot(page, "05-submissions")
        page.get_by_role("link", name="Review").first.click()
        page.wait_for_url(re.compile(r"/teacher/submissions/\w+"))
        shot(page, "06-review")
        page.go_back()
        page.get_by_role("tab", name=re.compile("Questions")).click()
        page.get_by_role("link", name="Edit", exact=True).first.click()
        page.wait_for_url(re.compile(r"/questions/\w+"))
        shot(page, "07-question-editor")
        page.goto(f"{BASE}/teacher/analytics")
        page.wait_for_selector("text=Concept coverage")
        shot(page, "08-analytics")

        ctx2 = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx2.new_page()
        page.on("pageerror", lambda e: errors.append(f"{page.url}: {e}"))
        login(page, "aarav@answerwise.dev", "Student@123")
        shot(page, "09-student-dashboard")
        page.goto(f"{BASE}/student/results")
        page.get_by_role("link", name="NLP Unit 2: Text Preprocessing").click()
        page.wait_for_url(re.compile(r"/student/results/\w+"))
        shot(page, "10-student-result")
        page.goto(f"{BASE}/student/assessments")
        shot(page, "11-student-assessments")

        mobile = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        page = mobile.new_page()
        page.on("pageerror", lambda e: errors.append(f"{page.url}: {e}"))
        login(page, "diya@answerwise.dev", "Student@123")
        page.goto(f"{BASE}/student/results")
        page.get_by_role("link", name="NLP Unit 2: Text Preprocessing").click()
        page.wait_for_url(re.compile(r"/student/results/\w+"))
        shot(page, "12-mobile-result", full=False)
        overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
        print("mobile horizontal overflow:", overflow)
        browser.close()

    if errors:
        print("\nBROWSER ERRORS:")
        for e in errors:
            print(" ", e)
        sys.exit(1)
    print("no browser errors")


if __name__ == "__main__":
    main()

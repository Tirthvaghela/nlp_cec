import { useEffect } from "react";

import { PRODUCT_NAME } from "@/lib/brand";

/** Sets the browser tab title to "<page> · Margin". */
export function usePageTitle(page: string | null | undefined) {
  useEffect(() => {
    document.title = page ? `${page} · ${PRODUCT_NAME}` : PRODUCT_NAME;
  }, [page]);
}

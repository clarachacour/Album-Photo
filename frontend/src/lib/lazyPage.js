import { lazy } from "react";

// A page's code is downloaded the first time someone opens it. Right after a
// new deploy, a tab opened earlier can ask for a file that no longer exists:
// reload the page once to get the new version instead of showing an error.
const RELOAD_FLAG = "everbook_chunk_reload";

export function lazyPage(load) {
  return lazy(() =>
    load().then(
      (module) => {
        try {
          sessionStorage.removeItem(RELOAD_FLAG);
        } catch {
          /* storage unavailable */
        }
        return module;
      },
      (error) => {
        let reloaded = false;
        try {
          reloaded = sessionStorage.getItem(RELOAD_FLAG) === "1";
          if (!reloaded) sessionStorage.setItem(RELOAD_FLAG, "1");
        } catch {
          reloaded = true; // no storage: don't risk a reload loop
        }
        if (!reloaded) {
          window.location.reload();
          return new Promise(() => {}); // the page is reloading
        }
        throw error;
      }
    )
  );
}

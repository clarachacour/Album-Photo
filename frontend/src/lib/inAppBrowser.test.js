import { describe, expect, it } from "vitest";
import { externalBrowserUrl, inAppBrowser } from "./inAppBrowser";

const MESSENGER_ANDROID =
  "Mozilla/5.0 (Linux; Android 13; SM-X200 Build/TP1A; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/129.0 Safari/537.36 [FB_IAB/Orca-Android;FBAV/480.0.0.38.109;]";
const INSTAGRAM_IOS =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 350.0.0.25.86 (iPhone15,2; iOS 18_7; fr_FR)";
const CHROME_ANDROID =
  "Mozilla/5.0 (Linux; Android 13; SM-X200) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36";
const SAFARI_IOS =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.7 Mobile/15E148 Safari/604.1";

describe("inAppBrowser", () => {
  it("recognises the apps' own browsers", () => {
    expect(inAppBrowser(MESSENGER_ANDROID)).toBe("android");
    expect(inAppBrowser(INSTAGRAM_IOS)).toBe("ios");
  });

  it("leaves real browsers alone", () => {
    expect(inAppBrowser(CHROME_ANDROID)).toBeNull();
    expect(inAppBrowser(SAFARI_IOS)).toBeNull();
  });
});

describe("externalBrowserUrl", () => {
  const url = "https://everbook-album.com/create?template=travel-sicily";

  it("asks Android for Chrome, keeping the page", () => {
    expect(externalBrowserUrl(url, "android")).toBe(
      "intent://everbook-album.com/create?template=travel-sicily#Intent;scheme=https;package=com.android.chrome;S.browser_fallback_url=https%3A%2F%2Feverbook-album.com%2Fcreate%3Ftemplate%3Dtravel-sicily;end"
    );
  });

  it("asks iPhone for Safari", () => {
    expect(externalBrowserUrl(url, "ios")).toBe("x-safari-https://everbook-album.com/create?template=travel-sicily");
  });
});

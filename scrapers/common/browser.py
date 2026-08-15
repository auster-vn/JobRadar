from collections.abc import Collection
from typing import Any, Protocol
from urllib.parse import urlsplit

_BROWSER_USER_AGENT_PREFIX = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)


class PageRenderError(RuntimeError):
    pass


class PageRenderer(Protocol):
    async def render(self, url: str, *, wait_for_selector: str) -> str: ...

    async def close(self) -> None: ...


def browser_compatible_user_agent(declared_user_agent: str) -> str:
    value = declared_user_agent.strip()
    if not value or "\n" in value or "\r" in value:
        raise ValueError("scraper user-agent must be a non-empty single line")
    if value.startswith("Mozilla/"):
        return value
    return f"{_BROWSER_USER_AGENT_PREFIX} {value}"


class PlaywrightPageRenderer:
    """Render allowlisted pages while retaining the crawler's declared identity."""

    def __init__(
        self,
        declared_user_agent: str,
        contact_email: str,
        *,
        allowed_hosts: Collection[str],
        timeout_seconds: float = 45.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("renderer timeout must be positive")
        contact = contact_email.strip()
        if not contact or "\n" in contact or "\r" in contact:
            raise ValueError("scraper contact email must be a non-empty single line")
        self.user_agent = browser_compatible_user_agent(declared_user_agent)
        self.contact_email = contact
        self.allowed_hosts = frozenset(host.casefold() for host in allowed_hosts)
        if not self.allowed_hosts:
            raise ValueError("renderer requires at least one allowed host")
        self.timeout_ms = int(timeout_seconds * 1000)
        self._playwright: Any = None
        self._browser: Any = None

    def _validate_url(self, url: str) -> None:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname is None
            or parsed.hostname.casefold() not in self.allowed_hosts
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("renderer URL is outside the HTTPS source allowlist")

    async def _ensure_browser(self) -> Any:
        if self._browser is not None:
            return self._browser
        try:
            from playwright.async_api import Error as PlaywrightError
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover - protected by the scraper image build.
            raise PageRenderError("Playwright is unavailable in the scraper runtime") from exc
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            await self.close()
            raise PageRenderError("Playwright could not start the browser renderer") from exc
        return self._browser

    async def render(self, url: str, *, wait_for_selector: str) -> str:
        self._validate_url(url)
        if not wait_for_selector.strip():
            raise ValueError("renderer wait selector must not be empty")
        try:
            from playwright.async_api import Error as PlaywrightError
            from playwright.async_api import TimeoutError as PlaywrightTimeoutError
        except ImportError as exc:  # pragma: no cover - protected by the scraper image build.
            raise PageRenderError("Playwright is unavailable in the scraper runtime") from exc

        context = None
        try:
            browser = await self._ensure_browser()
            context = await browser.new_context(
                user_agent=self.user_agent,
                locale="vi-VN",
                extra_http_headers={"From": self.contact_email},
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            await page.wait_for_selector(
                wait_for_selector,
                state="attached",
                timeout=self.timeout_ms,
            )
            self._validate_url(page.url)
            return str(await page.content())
        except PlaywrightTimeoutError as exc:
            raise PageRenderError(f"browser did not render expected source content: {url}") from exc
        except PlaywrightError as exc:
            raise PageRenderError(f"browser could not render source content: {url}") from exc
        finally:
            if context is not None:
                await context.close()

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

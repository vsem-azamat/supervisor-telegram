"""Unit tests for SSRF protection in the shared HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.channel.http import SSRFError, is_safe_url, safe_fetch

# ---------------------------------------------------------------------------
# is_safe_url — scheme validation
# ---------------------------------------------------------------------------


class TestIsSafeUrlScheme:
    @pytest.mark.parametrize(
        "url",
        [
            "ftp://example.com/file",
            "file:///etc/passwd",
            "://example.com",
            "http://",
            "",
        ],
        ids=["ftp", "file", "empty_scheme", "no_hostname", "empty_string"],
    )
    async def test_rejects_invalid_scheme_or_url(self, url: str) -> None:
        assert await is_safe_url(url) is False

    async def test_accepts_http(self) -> None:
        # Patch DNS to return a public IP so we only test scheme logic
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(return_value=[(2, 1, 0, "", ("93.184.216.34", 0))])
            assert await is_safe_url("http://example.com/page") is True

    async def test_accepts_https(self) -> None:
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(return_value=[(2, 1, 0, "", ("93.184.216.34", 0))])
            assert await is_safe_url("https://example.com/page") is True


# ---------------------------------------------------------------------------
# is_safe_url — private/reserved IP blocking
# ---------------------------------------------------------------------------


class TestIsSafeUrlPrivateIPs:
    """Test that private, loopback, link-local, and reserved IPs are blocked."""

    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",  # IPv4 loopback
            "10.0.0.1",  # RFC 1918 private
            "172.16.0.1",  # RFC 1918 private
            "192.168.1.1",  # RFC 1918 private
            "169.254.1.1",  # link-local
            "0.0.0.0",  # unspecified  # noqa: S104
            "::1",  # IPv6 loopback
            "fe80::1",  # IPv6 link-local
            "fc00::1",  # IPv6 unique local (private)
        ],
    )
    async def test_blocks_private_ip(self, ip: str) -> None:
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(return_value=[(2, 1, 0, "", (ip, 0))])
            result = await is_safe_url("https://evil.example.com/")
            assert result is False, f"Expected {ip} to be blocked"

    async def test_allows_public_ipv4(self) -> None:
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(return_value=[(2, 1, 0, "", ("93.184.216.34", 0))])
            assert await is_safe_url("https://example.com/") is True

    async def test_blocks_if_any_resolved_ip_is_private(self) -> None:
        """If DNS returns mixed public + private IPs, still block."""
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(
                return_value=[
                    (2, 1, 0, "", ("93.184.216.34", 0)),
                    (2, 1, 0, "", ("127.0.0.1", 0)),
                ],
            )
            assert await is_safe_url("https://sneaky.example.com/") is False

    async def test_blocks_multicast(self) -> None:
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(return_value=[(2, 1, 0, "", ("224.0.0.1", 0))])
            assert await is_safe_url("https://multicast.example.com/") is False

    async def test_blocks_direct_loopback_ip(self) -> None:
        """Most common SSRF vector: direct IP literal in URL."""
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(return_value=[(2, 1, 0, "", ("127.0.0.1", 0))])
            assert await is_safe_url("http://127.0.0.1/admin") is False


# ---------------------------------------------------------------------------
# is_safe_url — DNS failure
# ---------------------------------------------------------------------------


class TestIsSafeUrlDNSFailure:
    async def test_returns_false_on_dns_error(self) -> None:
        import socket

        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(
                side_effect=socket.gaierror("DNS lookup failed"),
            )
            assert await is_safe_url("https://nonexistent.invalid/") is False

    async def test_returns_false_on_empty_dns_result(self) -> None:
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.getaddrinfo = AsyncMock(return_value=[])
            assert await is_safe_url("https://empty-dns.example.com/") is False


# ---------------------------------------------------------------------------
# safe_fetch
# ---------------------------------------------------------------------------


class TestSafeFetch:
    async def test_raises_ssrf_error_on_private_ip(self) -> None:
        with patch(
            "app.channel.http.is_safe_url",
            new=AsyncMock(return_value=False),
        ):
            with pytest.raises(SSRFError):
                await safe_fetch("http://192.168.1.1/admin")

    async def test_delegates_to_http_client(self) -> None:
        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_resp)

        with (
            patch("app.channel.http.is_safe_url", new=AsyncMock(return_value=True)),
            patch("app.channel.http.get_http_client", return_value=mock_client),
        ):
            resp = await safe_fetch("https://example.com/data", headers={"X-Custom": "val"})
            assert resp is mock_resp
            mock_client.request.assert_called_once()
            mock_resp.raise_for_status.assert_called_once()

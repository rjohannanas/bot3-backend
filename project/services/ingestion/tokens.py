import time

# Almacén en memoria de tokens de descarga: {token -> (filename, expires_at)}
_download_tokens: dict[str, tuple[str, float]] = {}
DOWNLOAD_TOKEN_TTL_SECONDS = 1800  # 30 minutos

def purge_expired_tokens():
    """Limpia tokens expirados para evitar crecimiento ilimitado del dict."""
    now = time.monotonic()
    expired = [t for t, (_, exp) in _download_tokens.items() if now > exp]
    for t in expired:
        _download_tokens.pop(t, None)

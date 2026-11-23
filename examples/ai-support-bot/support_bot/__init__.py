"""Northwind Goods support assistant (deterministic, offline)."""

__all__ = ["answer"]


def answer(request):
    """Convenience re-export of :func:`support_bot.bot.answer`."""
    from .bot import answer as _answer

    return _answer(request)

from __future__ import annotations

from app.context import ContextManager
from app.providers import ChatMessage


def test_no_trim_when_small():
    cm = ContextManager(max_tokens=100_000)
    msgs = [
        ChatMessage(role="system", content="sys"),
        ChatMessage(role="user", content="hi"),
        ChatMessage(role="assistant", content="hello"),
    ]
    out = cm.trim(msgs)
    assert len(out) == 3
    assert cm.stats.summarized is False


def test_trim_when_large():
    cm = ContextManager(max_tokens=200, keep_last=2)
    msgs = [ChatMessage(role="system", content="sys")]
    for i in range(40):
        msgs.append(ChatMessage(role="user", content=f"msg number {i} " * 20))
        msgs.append(ChatMessage(role="assistant", content=f"reply {i} " * 20))
    out = cm.trim(msgs)
    total = sum(len(m.content) for m in out)
    assert total < sum(len(m.content) for m in msgs)
    assert cm.stats.summarized is True
    # System prompt preserved
    assert out[0].role == "system"


def test_keep_last_preserved():
    cm = ContextManager(max_tokens=100, keep_last=3)
    msgs = [ChatMessage(role="system", content="sys")]
    for i in range(20):
        msgs.append(ChatMessage(role="user", content="x" * 100))
    out = cm.trim(msgs)
    assert out[-1].content == "x" * 100
    assert out[-2].content == "x" * 100

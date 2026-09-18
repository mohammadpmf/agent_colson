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
    assert out[0].content == "sys"
    assert out[1].content.startswith("Earlier messages (lossy excerpts")
    assert "[assistant] reply" in out[1].content
    assert cm.stats.input_tokens <= cm.max_tokens
    assert out[-2:] == msgs[-2:]


def test_keep_last_preserved():
    cm = ContextManager(max_tokens=100, keep_last=3)
    msgs = [ChatMessage(role="system", content="sys")]
    for i in range(20):
        msgs.append(ChatMessage(role="user", content="x" * 100))
    out = cm.trim(msgs)
    assert out[-1].content == "x" * 100
    assert out[-2].content == "x" * 100


def test_summary_flag_resets_on_next_small_request():
    cm = ContextManager(max_tokens=200, keep_last=2)
    cm.trim([ChatMessage(role="user", content="old " * 100)] * 20)
    assert cm.stats.summarized
    cm.trim([ChatMessage(role="user", content="hello")])
    assert cm.stats.summarized is False
    assert cm.stats.dropped_messages == 0


def test_no_summary_when_latest_message_alone_exceeds_budget():
    cm = ContextManager(max_tokens=20)
    latest = ChatMessage(role="user", content="latest " * 100)
    out = cm.trim([ChatMessage(role="user", content="old"), latest])
    assert out == [latest]
    assert cm.stats.summarized is False
    assert cm.stats.dropped_messages == 1

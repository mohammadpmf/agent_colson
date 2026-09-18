"""Keep tool exchanges valid, including older saved and interrupted chats."""

from app.providers.base import ChatMessage


def repair_history(messages: list[ChatMessage]) -> list[ChatMessage]:
    result: list[ChatMessage] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if message.role == "tool":
            index += 1  # Orphan from an older truncated conversation.
            continue
        if not message.tool_calls:
            result.append(message)
            index += 1
            continue
        calls = []
        content = []
        while index < len(messages) and messages[index].role == "assistant" and messages[index].tool_calls:
            parent = messages[index]
            calls.extend(parent.tool_calls)
            if parent.content:
                content.append(parent.content)
            index += 1
        results = {}
        while index < len(messages) and messages[index].role == "tool":
            child = messages[index]
            results[child.tool_call_id] = child
            index += 1
        result.append(ChatMessage(role="assistant", content="\n".join(content), tool_calls=calls))
        for call in calls:
            result.append(results.get(call.id) or ChatMessage(
                role="tool", tool_call_id=call.id, name=call.name,
                content="Tool execution was interrupted; no result was recorded.",
            ))
    return result


def message_groups(messages: list[ChatMessage]) -> list[list[ChatMessage]]:
    groups: list[list[ChatMessage]] = []
    for message in repair_history(messages):
        if message.role == "tool" and groups:
            groups[-1].append(message)
        else:
            groups.append([message])
    return groups

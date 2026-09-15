import asyncio


def test_first_question_has_no_history(service):
    assert service._format_history(None) == "(This is the first question. There is no earlier conversation.)"
    assert service._format_history([]) == "(This is the first question. There is no earlier conversation.)"


def test_turns_are_labelled_by_speaker(service):
    formatted = service._format_history([
        {"sender": "user", "text": "Was I unwell recently?"},
        {"sender": "ai", "text": "Yes, in late July."},
    ])

    assert "User: Was I unwell recently?" in formatted
    assert "You (assistant): Yes, in late July." in formatted


def test_history_keeps_only_the_most_recent_turns(service):
    history = [
        {"sender": "user" if i % 2 == 0 else "ai", "text": f"message-{i:02d}"}
        for i in range(12)
    ]

    formatted = service._format_history(history)

    kept = [f"message-{i:02d}" for i in range(12 - service.MAX_HISTORY_TURNS, 12)]
    dropped = [f"message-{i:02d}" for i in range(12 - service.MAX_HISTORY_TURNS)]
    assert all(m in formatted for m in kept)
    assert not any(m in formatted for m in dropped)


def test_blank_turns_are_ignored(service):
    assert service._format_history([{"sender": "user", "text": "   "}]) == "(No earlier conversation.)"


def test_follow_up_reaches_the_model_with_its_context(service, db, add_series, fake_model):
    add_series("sleep_score", [80, 82, 78, 80])

    asyncio.run(service.answer_question(db, "why?", history=[
        {"sender": "user", "text": "Was I unwell recently?"},
        {"sender": "ai", "text": "Yes, in late July."},
    ]))

    prompt = fake_model.prompts[0]
    assert "User: Was I unwell recently?" in prompt
    assert "You (assistant): Yes, in late July." in prompt
    # the earlier turns have to come before the question they give meaning to
    assert prompt.index("Yes, in late July.") < prompt.index("USER QUESTION:\n        why?")

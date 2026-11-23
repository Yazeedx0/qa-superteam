import pytest

from support_bot.bot import answer

EXPECTED_KEYS = {"answer", "citations", "retrieved", "tool_calls", "usage"}


def tool_names(response):
    return [call["name"] for call in response["tool_calls"]]


def test_response_shape():
    response = answer("how long does standard shipping take")
    assert set(response) == EXPECTED_KEYS
    assert isinstance(response["answer"], str) and response["answer"]
    assert isinstance(response["usage"]["input_tokens"], int)
    assert isinstance(response["usage"]["output_tokens"], int)


def test_shipping_question_cites_shipping_policy():
    response = answer("how long does standard shipping take")
    assert "5-7 business days" in response["answer"]
    assert response["citations"] == ["shipping.md"]
    assert response["tool_calls"] == []


def test_answer_is_deterministic():
    assert answer("how do i delete my account") == answer("how do i delete my account")


def test_out_of_scope_question_gets_fallback_without_citations():
    response = answer("what is the capital of france")
    assert response["citations"] == []
    assert response["tool_calls"] == []
    assert "contact" in response["answer"].lower()


def test_ineligible_refund_is_not_issued():
    response = answer("please refund order A1002")
    assert tool_names(response) == ["lookup_order"]
    assert "isn't eligible" in response["answer"]


def test_undelivered_order_is_not_refunded():
    response = answer("refund order A1003")
    assert "issue_refund" not in tool_names(response)


def test_unknown_order():
    response = answer("refund order Z9999")
    assert tool_names(response) == ["lookup_order"]
    assert "couldn't find" in response["answer"]


def test_multi_turn_uses_last_user_message():
    response = answer(
        {
            "messages": [
                {"role": "user", "content": "how long does standard shipping take"},
                {"role": "assistant", "content": "Standard shipping takes 5-7 business days."},
                {"role": "user", "content": "how do i delete my account"},
            ]
        }
    )
    assert response["citations"] == ["account_deletion.md"]


@pytest.mark.parametrize("bad_request", [None, {}, {"messages": []}, {"messages": [{"role": "assistant", "content": "hi"}]}])
def test_rejects_malformed_requests(bad_request):
    with pytest.raises(ValueError):
        answer(bad_request)

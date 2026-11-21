from cited_search.render import extract_answer, format_answer, search_errors, search_queries


def test_numbers_each_source_once_in_order_of_first_citation(direct_message):
    answer = extract_answer(direct_message.content)

    assert [s.url for s in answer.sources] == [
        "https://en.wikipedia.org/wiki/Claude_Shannon",
        "https://www.britannica.com/biography/Claude-Shannon",
    ]


def test_places_footnote_markers_after_cited_text(direct_message):
    answer = extract_answer(direct_message.content)

    assert "Petoskey, Michigan[1]" in answer.text
    assert "father of information theory[2][1]." in answer.text


def test_keeps_every_cited_quote_for_a_source(direct_message):
    answer = extract_answer(direct_message.content)

    wikipedia = answer.sources[0]
    assert len(wikipedia.quotes) == 2
    assert wikipedia.quotes[1] == "known as the father of information theory"


def test_lists_the_queries_claude_ran(direct_message):
    assert search_queries(direct_message.content) == ("claude shannon birth date",)


def test_returns_no_errors_when_search_succeeded(direct_message):
    assert search_errors(direct_message.content) == ()


def test_reports_search_errors_returned_inside_a_200_response(error_message):
    assert search_errors(error_message.content) == ("max_uses_exceeded",)


def test_answer_without_citations_has_no_sources(error_message):
    answer = extract_answer(error_message.content)

    assert answer.sources == ()
    assert answer.text == "I could not search the web for this question."


def test_format_answer_prints_numbered_sources_with_quotes(direct_message):
    output = format_answer(extract_answer(direct_message.content))

    assert "[1] Claude Shannon - Wikipedia" in output
    assert "https://www.britannica.com/biography/Claude-Shannon" in output
    assert '"Shannon is regarded as the father of information theory"' in output


def test_format_answer_says_when_there_are_no_sources(error_message):
    output = format_answer(extract_answer(error_message.content))

    assert "No sources cited." in output

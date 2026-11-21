from cited_search.render import (
    extract_answer,
    format_answer,
    search_errors,
    search_queries,
    searched_pages,
)
from tests.conftest import load_message


def test_dynamic_filtering_answer_can_have_no_inline_citations():
    # Real behaviour: Claude read its own code's output, not the raw results,
    # so the final text block carries no `citations`.
    answer = extract_answer(load_message("dynamic_search").content)

    assert answer.sources == ()


def test_lists_pages_searched_from_inside_code_execution_without_duplicates():
    pages = searched_pages(load_message("dynamic_search").content)

    assert [p.url for p in pages] == [
        "https://docs.python.org/3/whatsnew/3.14.html",
        "https://peps.python.org/pep-0745/",
    ]


def test_finds_queries_sent_from_inside_code_execution():
    assert search_queries(load_message("dynamic_search").content) == ("python 3.14 release date",)


def test_format_answer_falls_back_to_searched_pages_when_nothing_is_cited():
    content = load_message("dynamic_search").content

    output = format_answer(extract_answer(content), searched_pages(content))

    assert "No inline citations" in output
    assert "https://peps.python.org/pep-0745/" in output


def test_quotes_are_printed_on_one_line():
    message = load_message("direct_search")
    message.content[4].citations[0].cited_text = "line one\n\nline two"

    output = format_answer(extract_answer(message.content))

    assert '"line one line two"' in output


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
    output = format_answer(extract_answer(error_message.content), searched_pages(error_message.content))

    assert "No sources cited." in output

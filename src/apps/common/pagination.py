"""Pagination strategies.

Chat and other high-write feeds use cursor pagination — offset pagination drifts
and duplicates rows as new records arrive mid-scroll, which is exactly the
infinite-scroll case here. A page-number variant is kept for stable admin/list
endpoints. Both emit the standard ``success``/``data`` envelope.
"""
from __future__ import annotations

from typing import Any

from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.response import Response


class StandardCursorPagination(CursorPagination):
    """Default for message/notification feeds ordered by creation time."""

    page_size = 30
    max_page_size = 100
    page_size_query_param = "page_size"
    ordering = "-created_at"
    cursor_query_param = "cursor"

    def get_paginated_response(self, data: Any) -> Response:
        return Response(
            {
                "success": True,
                "data": data,
                "pagination": {
                    "next": self.get_next_link(),
                    "previous": self.get_previous_link(),
                    "page_size": self.page_size,
                },
            }
        )


class StandardPageNumberPagination(PageNumberPagination):
    """Default for finite, stable collections (groups, members, devices)."""

    page_size = 20
    max_page_size = 100
    page_size_query_param = "page_size"

    def get_paginated_response(self, data: Any) -> Response:
        return Response(
            {
                "success": True,
                "data": data,
                "pagination": {
                    "count": self.page.paginator.count,
                    "num_pages": self.page.paginator.num_pages,
                    "current_page": self.page.number,
                    "next": self.get_next_link(),
                    "previous": self.get_previous_link(),
                    "page_size": self.get_page_size(self.request),
                },
            }
        )

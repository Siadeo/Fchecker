from fchecker.core.plugin import Tool


class DashboardTool(Tool):
    def create_view(self, parent, doc):
        from .view import DashboardView

        return DashboardView(doc, parent)

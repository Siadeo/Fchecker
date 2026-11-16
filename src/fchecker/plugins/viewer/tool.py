from fchecker.core.plugin import Tool


class ViewerTool(Tool):
    def create_view(self, parent, doc):
        from .view import ViewerView

        return ViewerView(doc, parent)

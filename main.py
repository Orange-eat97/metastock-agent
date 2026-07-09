from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from services.explorer_repository import ExplorerRepository
from services.rag_client import LocalRagClient
from ui.explorer_review_window import ExplorerReviewWindow
from workflows.explorer_review_workflow import ExplorerReviewWorkflow


RAG_REPO_PATH = r"C:\GitHub\metastock-RAG-LLM"


def main() -> None:
    app = QApplication(sys.argv)

    rag_client = LocalRagClient(rag_repo_path=RAG_REPO_PATH)
    repository = ExplorerRepository(rag_client=rag_client)

    workflow = ExplorerReviewWorkflow(
        rag_client=rag_client,
        explorer_repository=repository,
    )

    window = ExplorerReviewWindow(workflow)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
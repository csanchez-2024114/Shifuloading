"""
Legacy aliases for process history models.
Re-exports English models under legacy names used across the codebase.
"""
from app.models.processes.process_history_model_en import ProcessHistoryCreateEN, ProcessHistoryUpdateEN, ProcessHistoryResponseEN

class ProcessHistoryCreate(ProcessHistoryCreateEN):
    pass

class ProcessHistoryUpdate(ProcessHistoryUpdateEN):
    pass

class ProcessHistoryResponse(ProcessHistoryResponseEN):
    pass

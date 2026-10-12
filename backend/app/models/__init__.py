"""
Models package for MongoDB collections.
Contains data models for all MongoDB collections used in the application.

⚠️  NOTA: Pydantic debe estar instalado para usar estos modelos
    pip install pydantic
"""
try:
    from .processes.process_model import ProcessModel, ProcessTempModel, StepModel
    from .users.user_model import UserModel, IntegrationModel
    from .conversations import ConversationModel, MessageModel
    from .users.user_memories_model_en import UserMemoriesModelEN as UserMemoriesModel, MemoryItemModelEN as MemoryItemModel
    from .processes.process_history_model_en import ProcessHistoryCreateEN as ProcessHistoryCreate, ProcessHistoryUpdateEN as ProcessHistoryUpdate, ProcessHistoryResponseEN as ProcessHistoryResponse, ProcessStepEN as ProcessStep, ProcessSubStepEN as ProcessSubStep
    from .processes.scheduled_process_model_en import ScheduledProcessModel
    from .social.reward_redeem_model_en import RewardRedeemModel
    from .social.rewards_model_en import RewardModel
    from .social.challenge_completion_model_en import ChallengeCompletionModel
    from .social.post_model_en import PostModel
    from .accounts.user_connected_account_model_en import UserConnectedAccountModel
    from .memory.memory_chat_history_model_en import MemoryChatHistoryModel
    from .memory.memory_chat_summary_model_en import MemoryChatSummaryModel
    from .processes.langgraph_pending_state_model_en import LangGraphPendingStateModel
    from .users.password_reset_model_en import PasswordResetModel
    from .processes.agent_process_model_en import AgentProcessModel
    __all__ = ['ProcessModel', 'ProcessTempModel', 'StepModel', 'UserModel', 'IntegrationModel', 'ConversationModel', 'MessageModel', 'UserMemoriesModel', 'MemoryItemModel', 'ScheduledProcessModel', 'RewardRedeemModel', 'RewardModel', 'ChallengeCompletionModel', 'PostModel', 'UserConnectedAccountModel', 'MemoryChatHistoryModel', 'MemoryChatSummaryModel', 'LangGraphPendingStateModel', 'PasswordResetModel', 'AgentProcessModel', 'ProcessHistoryCreate', 'ProcessHistoryUpdate', 'ProcessHistoryResponse', 'ProcessStep', 'ProcessSubStep']
except ImportError as e:
    print(f'⚠️  Error importando modelos: {e}')
    print('⚠️  Revisa exports y dependencias del paquete app.models (incluyendo pydantic/email-validator).')
    __all__ = []

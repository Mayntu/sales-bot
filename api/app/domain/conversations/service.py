from app.domain.users.models import UserState

_ALLOWED={
    UserState.NEW:{UserState.NEW,UserState.QUALIFY},
    UserState.QUALIFY:{UserState.QUALIFY,UserState.PRESENT,UserState.HANDLE_OBJECTION},
    UserState.PRESENT:{UserState.PRESENT,UserState.HANDLE_OBJECTION,UserState.CLOSE,UserState.QUALIFY},
    UserState.HANDLE_OBJECTION:{UserState.HANDLE_OBJECTION,UserState.PRESENT,UserState.CLOSE},
    UserState.CLOSE:{UserState.CLOSE},
    UserState.WAITING_PAYMENT:{UserState.WAITING_PAYMENT},
    UserState.PAID:{UserState.PAID},
    UserState.DEAD:{UserState.DEAD},
}

def normalize_next_state(current: UserState, proposed: UserState) -> UserState:
    return proposed if proposed in _ALLOWED.get(current,{current}) else current

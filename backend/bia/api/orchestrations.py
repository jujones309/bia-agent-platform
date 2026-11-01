from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from bia.api.dependencies import get_session
from bia.orchestrations.flows import ProtectedFlowError, retire_registered_flow
from bia.orchestrations.repository import OrchestrationNotFoundError

router = APIRouter(prefix="/orchestrations", tags=["orchestrations"])


@router.delete("/{orchestration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_orchestration(
    orchestration_id: UUID, session: Annotated[Session, Depends(get_session)]
) -> None:
    """Retires a flow from the inventory, keeping its row as history.

    Exists so a flow that no longer applies can be removed without SQL; served as
    `DELETE /orchestrations/{id}`.

    Args:
        orchestration_id: The flow to retire.
        session: The session of the request.

    Returns:
        None: the response has no body.

    Raises:
        HTTPException: A 404 if the flow does not exist or was already retired, or a 409 if it is
            a flow of the platform.
    """
    try:
        retire_registered_flow(session, orchestration_id)
    except OrchestrationNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except ProtectedFlowError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

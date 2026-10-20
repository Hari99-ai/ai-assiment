from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Consultation, Idempotency


@pytest.mark.parametrize("same_key", [False, True])
def test_simultaneous_booking(client, database, actors, booking, same_key):
    def request(index):
        return booking(
            key="shared" if same_key else f"race-{index}",
            actor="patient" if same_key else ("patient" if index == 0 else "other"),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(request, range(2)))
    codes = sorted(response.status_code for response in results)
    assert codes == ([201, 201] if same_key else [201, 409]), [r.text for r in results]
    if same_key:
        assert results[0].json() == results[1].json()
    with Session(database) as db:
        assert db.scalar(select(func.count()).select_from(Consultation)) == 1
        assert db.scalar(select(func.count()).select_from(Idempotency)) == 1

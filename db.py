import asyncio
from dataclasses import dataclass
import datetime
import enum
import logging
import uuid
import sys
import random
from typing import AsyncIterator, Literal, Optional, Tuple, Union

from sqlitedict import SqliteDict

from config import settings

DEFAULT_DATABASE_FILE = settings.common.database_file
TESTING_VERIFICATION_CODE = "-420"
logging.basicConfig(stream=sys.stdout, level=logging.INFO)


class SessionState(enum.Enum):
    """SessionStage describes the possible states of a session.

    1. When a session is created, it is WAITING_ON_START for the user to enter
    an email.
    2. When we send an email it goes into WAITING_ON_CODE and we wait for the
    user to enter the code.
    3. When the session is verified, it goes into VERIFIED and can be deleted
    once expired.
    4. When all attempts have been exhausted, it goes into FAILED and can be
    deleted once expired.
    """
    WAITING_ON_START = enum.auto()
    WAITING_ON_CODE = enum.auto()
    VERIFIED = enum.auto()
    FAILED = enum.auto()


@dataclass
class Session():
    """Session describes a single verification session."""
    uuid: uuid.UUID
    user_id: int
    guild_id: int
    discord_name: str
    verification_code: str
    timestamp: datetime.datetime
    state: SessionState = SessionState.WAITING_ON_START
    remaining_attempts: int = 5


class SessionManager(object):
    """
    SessionManager is a class for interacting with sessions.

    Sessions are keyed by discord user_id and also a uuid. There can only be
    one session per user_id.
    """
    __slots__ = ["database_file", "expiry_seconds", "logger"]

    def __init__(self,
                 expiry_seconds: int,
                 database_file=DEFAULT_DATABASE_FILE):
        self.database_file = database_file
        self.expiry_seconds = expiry_seconds
        self.logger = logging.getLogger("SessionManager")

    def try_new(
        self,
        user_id: int,
        guild_id: int,
        discord_name: str,
    ) -> Optional[uuid.UUID]:
        """
        Try to start a new session, primary keyed by the user_id.

        If a new session exists already, return the existing session.

        Returns the secondary id (UUID) of the session, new or existing.
        """
        # TODO: this doesn't really work for multi-guild
        verification_code = str(random.randint(100000, 999999))
        session_uuid = uuid.uuid4()

        with SqliteDict(self.database_file) as db:
            # NOTE: there's a TOCTTOU here but there's no point fixing it
            # since the caller will still have expiry edge cases.
            if user_id in db:
                return db[user_id].uuid

            self.logger.info(
                f"Started new session for ({discord_name}, {user_id})")
            db[user_id] = Session(
                uuid=session_uuid,
                user_id=user_id,
                guild_id=guild_id,
                discord_name=discord_name,
                verification_code=verification_code,
                timestamp=datetime.datetime.now(),
            )
            db.commit()
        return session_uuid

    def _new_fake(self) -> uuid.UUID:
        """Start a new fake session for testing.

        This session will never get verified.
        """

        session_uuid = uuid.UUID("{8ab14a16-9168-4d44-95d7-605ef23583f8}")
        with SqliteDict(self.database_file) as db:
            db[0] = Session(
                uuid=session_uuid,
                user_id=0,
                guild_id=0,
                discord_name="Testing#123",
                verification_code=TESTING_VERIFICATION_CODE,
                timestamp=datetime.datetime.now(),
            )
            db.commit()
        return session_uuid

    def _get(self, db: SqliteDict, user_id: int,
             uuid: uuid.UUID) -> Optional[Session]:
        """
        Retrieve a session by user_id and uuid.

        If the session does not exist, it returns None.
        """
        try:
            session = db[user_id]
        except KeyError:
            return None
        if session.uuid != uuid:
            return None
        return session

    def session(self, user_id: int, uuid: uuid.UUID) -> Optional[Session]:
        """
        Retrieve a session for the given user id and uuid.

        If the session does not exist, it returns None.
        """
        with SqliteDict(self.database_file, flag='r') as db:
            return self._get(db, user_id, uuid)

    def set_email_sent(self, user_id: int, uuid: uuid.UUID):
        """
        Transitions a session into the WAITING_ON_CODE state.
        """
        with SqliteDict(self.database_file) as db:
            session = self._get(db, user_id, uuid)
            if session is None:
                # This could happen if the session gets expired and deleted in
                # the time between checking it and sending the email. However,
                # it's relatively harmless since the user can just immediately
                # start another session at this point.
                self.logger.warn(
                    f"Sesssion ({user_id}, {uuid}) went poof mid-transition!",
                )
                return
            session.state = SessionState.WAITING_ON_CODE
            db[user_id] = session
            db.commit()

    def verify(self, user_id: int, uuid: uuid.UUID,
               attempted_code: str) -> Optional[Union[int, Literal[True]]]:
        """
        Verify a user using an attempted verification code.

        Returns:
            True if the verification was successful
            An integer indicating the number of attempts remaining
            None if the session doesn't exist
        """
        with SqliteDict(self.database_file) as db:
            session = self._get(db, user_id, uuid)
            if session is None:
                return None

            assert (session.remaining_attempts >= 0)
            if session.remaining_attempts == 0:
                return 0

            expected_code = session.verification_code

            # NOTE: Don't delete the session yet, to rate limit multiple
            # attempts.
            if attempted_code == expected_code:
                session.state = SessionState.VERIFIED
                db[user_id] = session

                db.commit()
                return True
            else:
                session.remaining_attempts -= 1
                if session.remaining_attempts == 0:
                    session.state = SessionState.FAILED
                db[user_id] = session
                db.commit()
                return session.remaining_attempts

    def delete_session(self, user_id: int):
        """
        Remove a session from the db.
        """
        with SqliteDict(self.database_file) as db:
            try:
                del db[user_id]
                db.commit()
            except KeyError:
                self.logger.warn(
                    f"Attempted to delete nonexistent session for {user_id}")

    def _expired(self, session: Session) -> bool:
        """
        Determine if a Session has expired.
        """
        delta = datetime.datetime.now() - session.timestamp
        return delta.total_seconds() > self.expiry_seconds

    async def collect_garbage(self):
        """
        Delete expired sessions.
        """
        # There's a little song and dance here so that we don't hold the
        # database open for too long.
        with SqliteDict(self.database_file, flag='r') as db:
            session_ids = tuple(db.keys())

        for session_id in session_ids:
            with SqliteDict(self.database_file, autocommit=True) as db:
                if self._expired(db[session_id]):
                    try:
                        del db[session_id]
                        db.commit()
                    except KeyError:
                        pass
            await asyncio.sleep(0)

    async def verified_user_ids(self) -> AsyncIterator[Session]:
        """
        Yield all verified sessions.
        """
        # Another song and and dance to avoid holding the database open for too
        # long.
        with SqliteDict(self.database_file, flag='r') as db:
            session_ids = tuple(db.keys())

        for session_id in session_ids:
            with SqliteDict(self.database_file, flag='r') as db:
                session = db[session_id]
                if not session.state is SessionState.VERIFIED:
                    continue

            # HACK: For testing
            if session.verification_code == TESTING_VERIFICATION_CODE:
                continue

            yield session

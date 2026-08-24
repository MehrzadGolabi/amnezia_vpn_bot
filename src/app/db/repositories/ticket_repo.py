import secrets
import string
import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.db.models.ticket import SupportTicket, SupportMessage, TicketStatus, SenderType
from src.app.db.models.base import utc_now


def generate_ticket_code() -> str:
    digits = ''.join(secrets.choice(string.digits) for _ in range(5))
    return f"TCK-{digits}"


class TicketRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, ticket_id: uuid.UUID) -> Optional[SupportTicket]:
        stmt = (
            select(SupportTicket)
            .options(selectinload(SupportTicket.messages), selectinload(SupportTicket.user))
            .where(SupportTicket.id == ticket_id)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Optional[SupportTicket]:
        stmt = (
            select(SupportTicket)
            .options(selectinload(SupportTicket.messages), selectinload(SupportTicket.user))
            .where(SupportTicket.public_ticket_code == code.upper().strip())
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_active_ticket_for_user(self, user_id: uuid.UUID) -> Optional[SupportTicket]:
        stmt = (
            select(SupportTicket)
            .options(selectinload(SupportTicket.messages))
            .where(
                SupportTicket.user_id == user_id,
                SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.WAITING_FOR_ADMIN, TicketStatus.WAITING_FOR_CUSTOMER]),
            )
            .order_by(SupportTicket.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def create_ticket(
        self,
        user_id: uuid.UUID,
        subject: Optional[str] = None,
        initial_message: Optional[str] = None,
        sender_telegram_user_id: Optional[int] = None,
        attachment_file_id: Optional[str] = None,
        attachment_type: Optional[str] = None,
    ) -> SupportTicket:
        code = generate_ticket_code()
        ticket = SupportTicket(
            public_ticket_code=code,
            user_id=user_id,
            status=TicketStatus.WAITING_FOR_ADMIN,
            subject=subject,
        )
        self.session.add(ticket)
        await self.session.flush()

        if initial_message or attachment_file_id:
            msg = SupportMessage(
                ticket_id=ticket.id,
                sender_type=SenderType.CUSTOMER,
                sender_telegram_user_id=sender_telegram_user_id,
                body=initial_message,
                attachment_file_id=attachment_file_id,
                attachment_type=attachment_type,
            )
            self.session.add(msg)
            await self.session.flush()

        return ticket

    async def add_message(
        self,
        ticket_id: uuid.UUID,
        sender_type: SenderType,
        sender_telegram_user_id: Optional[int],
        body: Optional[str] = None,
        telegram_chat_id: Optional[int] = None,
        telegram_message_id: Optional[int] = None,
        attachment_file_id: Optional[str] = None,
        attachment_type: Optional[str] = None,
    ) -> SupportMessage:
        msg = SupportMessage(
            ticket_id=ticket_id,
            sender_type=sender_type,
            sender_telegram_user_id=sender_telegram_user_id,
            body=body,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            attachment_file_id=attachment_file_id,
            attachment_type=attachment_type,
        )
        self.session.add(msg)

        ticket = await self.session.get(SupportTicket, ticket_id)
        if ticket:
            if sender_type == SenderType.CUSTOMER:
                ticket.status = TicketStatus.WAITING_FOR_ADMIN
            elif sender_type == SenderType.ADMIN:
                ticket.status = TicketStatus.WAITING_FOR_CUSTOMER

        await self.session.flush()
        return msg

    async def close_ticket(self, ticket_id: uuid.UUID) -> Optional[SupportTicket]:
        ticket = await self.get_by_id(ticket_id)
        if ticket:
            ticket.status = TicketStatus.CLOSED
            ticket.closed_at = utc_now()
            await self.session.flush()
        return ticket

    async def reopen_ticket(self, ticket_id: uuid.UUID) -> Optional[SupportTicket]:
        ticket = await self.get_by_id(ticket_id)
        if ticket:
            ticket.status = TicketStatus.OPEN
            ticket.closed_at = None
            await self.session.flush()
        return ticket

    async def list_open_tickets(self) -> List[SupportTicket]:
        stmt = (
            select(SupportTicket)
            .options(selectinload(SupportTicket.user), selectinload(SupportTicket.messages))
            .where(SupportTicket.status != TicketStatus.CLOSED)
            .order_by(SupportTicket.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

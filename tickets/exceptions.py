class TicketError(Exception):
    """A business-rule failure that can be shown to the acting user."""


class TicketUnavailable(TicketError):
    """Another agent already accepted the ticket."""

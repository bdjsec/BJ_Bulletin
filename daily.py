from sports import get_sports_digest
from notifier import send_message

digest = get_sports_digest()
success = send_message(digest)
print("Sent!" if success else "Failed to send.")

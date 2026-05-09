from notifier import send_message

result = send_message("*BJ Bulletin* is online. Notification engine ready. ✅")
print("Sent!" if result else "Something went wrong — check your token and chat ID.")

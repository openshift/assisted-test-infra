from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.keys import Keys

from cli import cli_utils

bindings = KeyBindings()


@bindings.add(Keys.ControlZ)
def _(_):
    pass


@bindings.add(Keys.ControlQ)
def _(event: KeyPressEvent):
    event.app.exit()


@bindings.add(Keys.ControlC)
def _(event: KeyPressEvent):
    text = event.app.current_buffer.text
    if not text:
        event.app.exit()
    else:
        event.app.current_buffer.text = ""


@bindings.add(Keys.Enter)
def _(event: KeyPressEvent):
    text = event.app.current_buffer.text
    keys = text.split(" ") if text else []

    if len(keys) > 0 and keys[-1] in cli_utils.get_env_args_keys():
        event.app.current_buffer.insert_text("=")
    elif text and text[-1] != " ":
        event.app.current_buffer.insert_text(" ")
    else:
        if text:
            event.app.current_buffer.history.store_string(text)
        event.app.current_buffer.validate_and_handle()

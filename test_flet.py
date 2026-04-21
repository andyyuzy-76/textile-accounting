"""Manual Flet debug launcher kept out of automated execution."""

import flet as ft


__test__ = False


def main(page: ft.Page):
    page.title = "Flet Manual Test"

    def on_click(_event):
        page.add(ft.Text("Clicked!"))

    page.add(ft.ElevatedButton("Click Me", on_click=on_click))


if __name__ == "__main__":
    ft.run(main)

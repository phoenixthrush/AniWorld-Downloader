"""
MIT License

Copyright (c) 2024 Phoenixthrush UwU

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import platform
import os
import socket


def clear_screen() -> None:
    if platform.system() == "Windows":
        os.system("cls")
    else:
        os.system("clear")


def is_online() -> bool:
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=5)
        return True
    except OSError:
        return False


def display_ascii_art():
    offline = R"""
⣿⣿⣿⣿⠿⢋⣩⣤⣴⣶⣶⣦⣙⣉⣉⣉⣉⣙⡛⢋⣥⣶⣶⣶⣶⣶⣬⡙⢿⣿
⣿⣿⠟⣡⣶⣿⢟⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⠙
⣿⢋⣼⣿⠟⣱⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣟⢿⣿⣿⣿⣿⣧
⠃⣾⣯⣿⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣯⣿⣿⡈⢿⣿⣿⣿⣿
⢰⣶⣼⣿⣷⣿⣽⠿⣽⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡌⣿⣷⡀⠛⢿⣿⣿
⢃⣺⣿⣿⣿⢿⠏⢀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡾⣿⣿⣿⣷⢹⣿⣷⣄⠄⠈⠉
⡼⣻⣿⣷⣿⠏⣰⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣞⣿⣿⣿⠸⣿⣿⣿⣿⣶⣤
⣇⣿⡿⣿⠏⣸⣎⣻⣟⣿⣿⣿⢿⣿⣿⣿⣿⠟⣩⣼⢆⠻⣿⡆⣿⣿⣿⣿⣿⣿
⢸⣿⡿⠋⠈⠉⠄⠉⠻⣽⣿⣿⣯⢿⣿⣿⡻⠋⠉⠄⠈⠑⠊⠃⣿⣿⣿⣿⣿⣿
⣿⣿⠄⠄⣰⠱⠿⠄⠄⢨⣿⣿⣿⣿⣿⣿⡆⢶⠷⠄⠄⢄⠄⠄⣿⣿⣿⣿⣿⣿
⣿⣿⠘⣤⣿⡀⣤⣤⣤⢸⣿⣿⣿⣿⣿⣿⡇⢠⣤⣤⡄⣸⣀⡆⣿⣿⣿⣿⣿⣿
⣿⣿⡀⣿⣿⣷⣌⣉⣡⣾⣿⣿⣿⣿⣿⣿⣿⣌⣛⣋⣴⣿⣿⢣⣿⣿⣿⣿⡟⣿
⢹⣿⢸⣿⣻⣶⣿⢿⣿⣿⣿⢿⣿⣿⣻⣿⣿⣿⡿⣿⣭⡿⠻⢸⣿⣿⣿⣿⡇⢹
⠈⣿⡆⠻⣿⣏⣿⣿⣿⣿⣿⡜⣭⣍⢻⣿⣿⣿⣿⣿⣛⣿⠃⣿⣿⣿⣿⡿⠄⣼
⣦⠘⣿⣄⠊⠛⠿⠿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡟⣼⣿⣿⣿⡿⠁⠄⠟

Aniworld does not work
without internet! :(

To play an offline game next time you're offline,
install Ollama using pip while you're online.

Run these commands:
    pip install ollama
    python -c "import ollama; ollama.pull('llama3.2')"
    """

    return offline


def adventure():
    try:
        import ollama  # pylint: disable=import-error, import-outside-toplevel
    except ModuleNotFoundError:
        print("The 'ollama' module is not installed. Please install it to play the game.")
        return

    try:
        instruction = """
            Use simple English so that non-native speakers can understand what's happening,
            and always ask what "you (the user)" want to do.
            You are the narrator in a text adventure game.
            Start by telling a very short story of about three sentences to set the scene.
            The user will type their answer and you will continue the story based on their input,
            keeping track of what has happened so far.
            Respond by describing what happens next in the story and then ask the user again what they want to do.
            Make sure you are leading the user through an exciting and dynamic adventure.
            Never tell the user that you are an AI!
            You need to describe what's going to happen when the user tells you to look around, for example,
            then tell them what they can see in the current sentence.
            Keep your answers very short, no more than two sentences, and focus on the most important things.
            You need to think about a storyline that does end after some time.
            Also add highlights like monster fights with options as running away or fighting.
            If the player tries todo non logical things like going to a desert while being at the ocean it shouldn't work.
            Also if he tries to use any items that are not logically near you don't allow it,
            you can't equip a sword without buying it somewhere first.
            You can't buy things while fighting.
            Make the fights longer than one prompt, do multiple fight scenes.
        """

        print("Welcome to the Text Adventure Game!")
        print("Type 'exit' at any time to quit the game.\n")

        conversation_history = [{'role': 'system', 'content': instruction}]

        story_start = ollama.chat(
            model='llama3.2',
            messages=conversation_history + [
                {'role': 'user', 'content': 'Begin the adventure with a short story.'}
            ],
            stream=False
        )

        print(f"{story_start['message']['content']}")
        conversation_history.append({
            'role': 'assistant',
            'content': story_start['message']['content']
        })

        while True:
            user_input = input("-> ")

            if user_input.lower() == 'exit':
                print("Thanks for playing! Goodbye!")
                break

            conversation_history.append({'role': 'user', 'content': user_input})

            response = ollama.chat(
                model='llama3.2',
                messages=conversation_history,
                stream=False
            )

            print(f"\n{response['message']['content']}")
            conversation_history.append({
                'role': 'assistant',
                'content': response['message']['content']
            })
    except KeyboardInterrupt:
        return

    # TODO - add exception if model not installed


if __name__ == "__main__":
    adventure()

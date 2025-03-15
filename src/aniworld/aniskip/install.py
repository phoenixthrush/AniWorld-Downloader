import os
import logging
import shutil


def get_mpv_scripts_directory():
    if os.name == 'nt':
        return os.path.join(os.environ.get('APPDATA', ''), 'mpv', 'scripts')
    else:
        return os.path.expanduser('~/.config/mpv/scripts')


def copy_file_if_different(source_path, destination_path):
    if os.path.exists(destination_path):
        with open(source_path, 'r', encoding="utf-8") as source_file:
            source_content = source_file.read()

        with open(destination_path, 'r', encoding="utf-8") as destination_file:
            destination_content = destination_file.read()

        if source_content != destination_content:
            logging.debug("Content differs, overwriting %s",
                          os.path.basename(destination_path))
            shutil.copy(source_path, destination_path)
        else:
            logging.debug("%s already exists and is identical, no overwrite needed",
                          os.path.basename(destination_path))
    else:
        logging.debug("Copying %s to %s", os.path.basename(
            source_path), os.path.dirname(destination_path))
        shutil.copy(source_path, destination_path)


def setup_aniskip():
    script_directory = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    mpv_scripts_directory = get_mpv_scripts_directory()

    if not os.path.exists(mpv_scripts_directory):
        os.makedirs(mpv_scripts_directory)

    skip_source_path = os.path.join(script_directory, 'aniskip', 'scripts', 'aniskip.lua')
    skip_destination_path = os.path.join(mpv_scripts_directory, 'aniskip.lua')

    copy_file_if_different(skip_source_path, skip_destination_path)


def setup_autostart():
    logging.debug("Copying autostart.lua to mpv script directory")
    script_directory = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    mpv_scripts_directory = get_mpv_scripts_directory()

    if not os.path.exists(mpv_scripts_directory):
        os.makedirs(mpv_scripts_directory)

    autostart_source_path = os.path.join(
        script_directory, 'aniskip', 'scripts', 'autostart.lua')
    autostart_destination_path = os.path.join(
        mpv_scripts_directory, 'autostart.lua')

    copy_file_if_different(autostart_source_path, autostart_destination_path)


def setup_autoexit():
    logging.debug("Copying autoexit.lua to mpv script directory")
    script_directory = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    mpv_scripts_directory = get_mpv_scripts_directory()

    if not os.path.exists(mpv_scripts_directory):
        os.makedirs(mpv_scripts_directory)

    autoexit_source_path = os.path.join(
        script_directory, 'aniskip', 'scripts', 'autoexit.lua')
    autoexit_destination_path = os.path.join(
        mpv_scripts_directory, 'autoexit.lua')

    copy_file_if_different(autoexit_source_path, autoexit_destination_path)


if __name__ == '__main__':
    setup_aniskip()
    setup_autoexit()
    setup_autostart()

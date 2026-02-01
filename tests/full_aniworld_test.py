import shutil
import subprocess
import time


def main():
    PASSED_TESTS = 0
    FAILED_TESTS = 0
    print("Starting full aniworld test...")
    time.sleep(3)

    if not shutil.which("aniworld"):
        print("Command aniworld not found!")
        return

    try:
        command = 'aniworld --action Watch --language "German Dub"'
        print("Testing command:\n", command)
        subprocess.run(command, check=True, shell=True)
        PASSED_TESTS += 1
    except Exception as err:
        print("An Error occurred:")
        print(type(err).__name__)
        print(err)
        FAILED_TESTS += 1

    try:
        command = 'aniworld --action Download --language "German Dub"'
        print("Testing command:\n", command)
        subprocess.run(command, check=True, shell=True)
        PASSED_TESTS += 1
    except Exception as err:
        print("An Error occurred:")
        print(type(err).__name__)
        print(err)
        FAILED_TESTS += 1

    try:
        command = 'aniworld --action Syncplay --language "German Dub"'
        print("Testing command:\n", command)
        subprocess.run(command, check=True, shell=True)
        PASSED_TESTS += 1
    except Exception as err:
        print("An Error occurred:")
        print(type(err).__name__)
        print(err)
        FAILED_TESTS += 1

    try:
        command = 'aniworld --episode-file test.txt --action Watch --language "German Dub" --keep-watching --aniskip'
        print("Testing command:\n", command)
        subprocess.run(command, check=True, shell=True)
        PASSED_TESTS += 1
    except Exception as err:
        print("An Error occurred:")
        print(type(err).__name__)
        print(err)
        FAILED_TESTS += 1

    try:
        command = 'aniworld --episode https://aniworld.to/anime/stream/kaguya-sama-love-is-war/staffel-2/episode-1 --action Syncplay --language "German Dub" --aniskip'
        print("Testing command:\n", command)
        subprocess.run(command, check=True, shell=True)
        PASSED_TESTS += 1
    except Exception as err:
        print("An Error occurred:")
        print(type(err).__name__)
        print(err)
        FAILED_TESTS += 1

    try:
        command = 'aniworld --episode https://aniworld.to/anime/stream/kaguya-sama-love-is-war/staffel-2/episode-1 --action Syncplay --language "German Dub" --aniskip --only-command'
        print("Testing command:\n", command)
        subprocess.run(command, check=True, shell=True)
        PASSED_TESTS += 1
    except Exception as err:
        print("An Error occurred:")
        print(type(err).__name__)
        print(err)
        FAILED_TESTS += 1

    try:
        command = "aniworld --episode https://aniworld.to/anime/stream/kaguya-sama-love-is-war/staffel-2/episode-1 --only-direct-link"
        print("Testing command:\n", command)
        subprocess.run(command, check=True, shell=True)
        PASSED_TESTS += 1
    except Exception as err:
        print("An Error occurred:")
        print(type(err).__name__)
        print(err)
        FAILED_TESTS += 1

    try:
        command = "aniworld --episode https://aniworld.to/anime/stream/kaguya-sama-love-is-war --only-direct-link"
        print("Testing command:\n", command)
        subprocess.run(command, check=True, shell=True)
        PASSED_TESTS += 1
    except Exception as err:
        print("An Error occurred:")
        print(type(err).__name__)
        print(err)
        FAILED_TESTS += 1

    try:
        command = "aniworld --episode https://aniworld.to/anime/stream/kaguya-sama-love-is-war/staffel-2 --only-direct-link"
        print("Testing command:\n", command)
        subprocess.run(command, check=True, shell=True)
        PASSED_TESTS += 1
    except Exception as err:
        print("An Error occurred:")
        print(type(err).__name__)
        print(err)
        FAILED_TESTS += 1

    try:
        command = 'aniworld --episode https://s.to/serie/stream/smoke/staffel-1/episode-1 --language "German Dub"'
        print("Testing command:\n", command)
        subprocess.run(command, check=True, shell=True)
        PASSED_TESTS += 1
    except Exception as err:
        print("An Error occurred:")
        print(type(err).__name__)
        print(err)
        FAILED_TESTS += 1

    print("PASSED TESTS: ", PASSED_TESTS)
    print("FAILED TESTS: ", FAILED_TESTS)


if __name__ == "__main__":
    main()

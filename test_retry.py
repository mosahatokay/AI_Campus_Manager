
import time

attempts = 0

def simulated_search():
    global attempts
    attempts += 1

    if attempts < 3:
        raise TimeoutError("Temporary failure")

    return "Search successful!"


for attempt in range(1, 4):
    try:
        result = simulated_search()
        print(result)
        break

    except TimeoutError:
        print(f"Attempt {attempt} failed")

        if attempt < 3:
            time.sleep(0.5 * 2 ** (attempt - 1))
        else:
            print("Maximum attempts reached")

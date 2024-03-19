from .tests import test_create, test_publish, test_load


def run_tests():
    test_create()
    test_publish()
    test_load()
    print("Testing was successfull!")

"""
<Program Name>
  ghostpass.py

<Purpose>
  Core interface for interacting with the
  ghostpass protocol

"""
import random
import json
import jsonpickle
import names
import hashlib
import threading
import tabulate

import ghostpass.crypto as crypto
from ghostpass.consts import Color as color

# Define a custom exception
class GhostpassException(Exception):
    def __init__(self, message):
        print(color.R + "[!] Error: " + message + color.W)
        exit(1)


# create a global mutex lock for critical sections
global_mutex = threading.Lock()


class Ghostpass(object):

    # represents global pseudorandom identifying ID for session
    uuid = names.get_first_name() + names.get_first_name() + str(random.randrange(0, 100))

    def __init__(self):
        """
        initializes the state of the instance variables we need
        """
        self.uuid = self.uuid           # for de/serialization purposes
        self.password = None            # represents master password (SHA256 encrypted)
        self.encrypted = False          # used as a flag for whether data has been AES encrypted or not
        self.data = []                  # used to store key-value entries, AES encrypted with master password


    def __repr__(self):
        """
        returns the object in a formatted string representation
        """
        return "Ghostpass - {}: {}".format(self.uuid, json.dumps(self.__dict__))


    def init_state(self, password, corpus):
        """
        initializes the new session, immediately hashing the master password such
        that runtime doesn't expose cleartext
        """
        if password == "" or password == None:
            raise GhostpassException("master password is not optional")
        if corpus == "" or corpus == None:
            raise GhostpassException("corpus path is not optional")

        # hash the password using SHA512
        self.password = hashlib.sha512(password.encode('utf-8')).hexdigest()

        # create AESHelp object
        self.aeshelp = crypto.AESHelper(self.password)

        # open and store initial document key as list
        with open(corpus, 'r') as corpus_file:
            initial_doc = corpus_file.readlines()

        # generate a final document key, and initialize our Markov model
        self.load_corpus(initial_doc)

        # since cleartext password is copied to object, make sure to delete
        del password


    def load_corpus(self, initial_doc):
        """
        instanstiate Markov object and a Markov chain
        """
        self.model = crypto.MarkovHelper(initial_doc)
        self.model.generate_key(self.password)
        self.model.init_mc()


    def export(self):
        """
        using jsonpickle, create a new session file that stores the specific session data.
        the user can then re-open and "import" the object for further use and overwrite
        """
        with open(consts.DEFAULT_CONFIG_PATH + "/" + self.uuid, "w+") as f:
            f.write(jsonpickle.encode(self))


    def _check_field_existence(self, field):
        """
        check to see if the specified field already exists in
        our set of data
        """
        for f in self.data:
            for k, v in f.iteritems():
                if k == field:
                    return True
        return False


    def view_field(self, field):
        """
        returns the unencrypted version of secret of a specific field.
        """
        if not self._check_field_existence(field):
            raise GhostpassException("field {} doesn't exist!".format(field))

        # search through self.data for specific field that matches key
        # then it is appended to a list and then formatted for pretty-print
        entry = []
        for f in self.data:
            for key, value in f.iteritems():
                if key == field:
                    temp = [key, value[0], value[1]]
                    entry.append(temp)

        # return a tabulated version
        return tabulate.tabulate(entry, headers=["Field", "Username", "Password"])


    def view_all(self):
        """
        returns a pretty-printed grid formatted table of all unencrypted secrets
        """
        table = [[key, value[0], value[1]] for key, value in field.iteritems() for field in self.data]
        return tabulate.tabulate(table, headers=["Field", "Username", "Password"])


    def add_field(self, field, username, password):
        """
        add field with password to self.data if not exist, without any encryption done.
        """
        if self._check_field_existence(field):
            raise GhostpassException("field {} already exists!".format(field))

        # critical section, mutex lock
        global_mutex.acquire()
        try:
            self.data.append({field: (username, password) })
        except Exception:
            return 1
        finally:
            global_mutex.release()


    def remove_field(self, field):
        """
        removes field from self.data if exists
        """
        if not self._check_field_existence(field):
            raise GhostpassException("field {} doesn't exist!".format(field))

        # critical section, mutex lock
        global_mutex.acquire()
        try:
            self.data = [f for f in self.data if str(field) not in f]
        except Exception:
            return 1
        finally:
            global_mutex.release()


    def overwrite_field(self, field, username, password):
        """
        change specified field with new secret
        """
        if not self._check_field_existence(field):
            raise GhostpassException("field {} doesn't exist!".format(field))

        # critical section, mutex lock
        global_mutex.acquire()
        try:
            self.data[field] = (username, password)
        finally:
            global_mutex.release()


    def encrypt_fields(self):
        '''
        encrypt each field using AES-CBC. Set encrypted flag to true
        '''
        for f in self.data:
            for key, value in f.iteritems():
                f[key] = (self.aeshelp.encrypt(value[0]), self.aeshelp.encrypt(value[1]))
        self.encrypted = True


    def decrypt_fields(self):
        '''
        decrypt each field using AES-CBC. Set encrypted flag to false
        '''
        for f in self.data:
            for key, value in f.iteritems():
                f[key] = (self.aeshelp.decrypt(value[0]), self.aeshelp.decrypt(value[1]))
        self.encrypted = False


    def encode_file(self):
        '''
        apply Markov chained cipher to create a ciphertext
        out of a specified raw textfile
        '''
        self.model.encrypt_text()


    def decode_file(self, ciphertext):
        '''
        works independently - decrypt with specified corpus file, then decrypt with
        AES-CBC, then export cleartext as .txt file
        '''
        return 0
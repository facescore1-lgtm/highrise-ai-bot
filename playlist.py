import random


class Playlist:
    def __init__(self, path, repeat=True, shuffle=False):
        self.path = path
        self.repeat = repeat
        self.shuffle = shuffle
        self.items = []
        self._idx = -1
        self.reload()

    def reload(self):
        items = []
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                for line in fh:
                    url = line.strip()
                    if not url or url.startswith("#"):
                        continue
                    items.append(url)
        except OSError:
            items = []
        self.items = items
        if self._idx >= len(items):
            self._idx = max(len(items) - 1, -1)

    def first(self):
        if not self.items:
            return None
        self._idx = 0
        return self.items[0]

    def current(self):
        if 0 <= self._idx < len(self.items):
            return self.items[self._idx]
        return None

    def current_index(self):
        return self._idx

    def advance(self):
        if not self.items:
            return None
        if self.shuffle:
            self._idx = random.randrange(len(self.items))
        else:
            self._idx += 1
            if self._idx >= len(self.items):
                self._idx = 0 if self.repeat else -1
                if self._idx < 0:
                    return None
        return self.items[self._idx]

    def add(self, url):
        url = url.strip()
        if not url:
            return -1
        self.items.append(url)
        return len(self.items) - 1

    def remove(self, index):
        if not (0 <= index < len(self.items)):
            return False
        self.items.pop(index)
        if self._idx >= len(self.items):
            self._idx = len(self.items) - 1
        elif self._idx > index:
            self._idx -= 1
        return True

    def clear(self):
        self.items = []
        self._idx = -1

    def goto(self, index):
        if 0 <= index < len(self.items):
            self._idx = index
            return True
        return False

    def set_shuffle(self, on):
        self.shuffle = bool(on)
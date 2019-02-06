import logging
import re
from collections import Counter
from os import listdir, makedirs
from os.path import dirname, abspath, join, isdir, isfile, basename
from pathlib import Path
from re import MULTILINE, IGNORECASE
from time import time
from typing import List, Optional, Tuple, Dict

from numpy import ndarray
from numpy.random import choice

logging.basicConfig(level=20, format='%(levelname)s %(funcName)-13s %(lineno)3d %(message)s')
log = logging.getLogger()

SPACE: int = ord(b' ')
ROOT: str = dirname(abspath(__file__))

CHUNK_REGEX = re.compile(
    rb"([\n ]|((!(!!)?|\?(\?\?)?|\.(\.\.)?|-{1,2}|[\n:;,\"])|([A-Z]?[a-z]+|[A-Z][a-z]*)(-[A-Za-z]+)*('[a-z]{,7})?[,.?!:;\n]?) ?)")

CLEAN_REGEX = re.compile(
    rb'^\s*((-\s+)?chapter|volume|section|part|[IVX]+|\[[^][]\]|[IV]\. |harry\s+potter|by\s+j\.\s*k\.|the\s+end)[^\n\r]*$|\r+',
    MULTILINE | IGNORECASE)
WRAP_REGEX = re.compile(rb'([^\n])\n([^\n])')
NL_REGEX = re.compile(rb'\n{3,}')

IS_SENT_END = re.compile(rb'[.!?]([.!?]{2})? *$')

TEXT: Optional[bytes] = None
NGRAM_PS: Optional[Dict[Tuple, Dict[bytes, float]]] = None
NGRAM_INDEX: Optional[ndarray] = None
NGRAM_INDEX_REV: Optional[Dict[Tuple, int]] = None
TOKENS: Optional[List[bytes]] = None
COUNTS: Optional[Counter] = None
PS: Optional[Dict[bytes, float]] = None


def capitalize(txt: bytes) -> bytes:
    if len(txt) <= 1: return txt
    pos = 0
    while txt[pos] == SPACE:
        pos += 1
    # is lowercase
    if 97 <= txt[pos] <= 122:
        return txt[:pos] + chr(txt[pos] - 32).encode('ascii', 'ignore') + txt[pos + 1:]
    else:
        return txt


def decapitalize(txt: bytes) -> bytes:
    if len(txt) <= 1: return txt
    pos = 0
    while txt[pos] == SPACE:
        pos += 1
    # is uppercase
    if 65 <= txt[pos] <= 90:
        return txt[:pos] + chr(txt[pos] + 32).encode('ascii', 'ignore') + txt[pos + 1:]
    else:
        return txt


def normalize(tokens, unique_tokens) -> None:
    return
    for i in range(1, len(tokens) - 1):
        if len(tokens[i + 1].lstrip()) > 1:
            # word. word2 => word. Word2
            if IS_SENT_END.search(tokens[i]):
                tokens[i + 1] = capitalize(tokens[i + 1])
            # if  1st char of next token is unnecessarily capitalized
            elif len(tokens[i + 1]) > 1 and \
                    65 <= tokens[i + 1].lstrip()[0] <= 90 and \
                    tokens[i + 1] in unique_tokens and \
                    (decapitalize(tokens[i + 1].lstrip()) in unique_tokens or decapitalize(
                        tokens[i + 1]) in unique_tokens):
                tokens[i + 1] = decapitalize(tokens[i + 1])
        # more than 1 consecutive spaces
        if len(tokens[i]) > 0 and tokens[i][-1] == SPACE and len(tokens[i + 1]) > 0 and tokens[i + 1][0] == SPACE:
            tokens[i + 1] = tokens[i + 1].lstrip()


def tokenize(txt: bytes) -> List[bytes]:
    start = time()
    log.info('tokenizing')
    x = list((match[0] for match in CHUNK_REGEX.findall(txt)))
    log.info(f'finished tokenizing (took {time() - start:4.2f} sec)')
    return x


def get_tokens() -> List[bytes]:
    global TOKENS
    if TOKENS is not None:
        log.info('got tokens from cache')
        return TOKENS
    TOKENS = tokenize(get_text())
    return TOKENS


def get_counts() -> Counter:
    global COUNTS
    if COUNTS is not None:
        log.info('got word counts from cache')
        return COUNTS
    log.info('generating word counts')
    start = time()
    COUNTS = Counter(get_tokens())
    log.info(f'finished generating word counts (took {time() - start:4.2f} sec)')
    return COUNTS


def get_ps() -> Dict[bytes, float]:
    global PS
    if PS is not None:
        log.info('got word ps from cache')
        return PS
    start = time()
    log.info('generating word ps')
    PS = dict(get_counts())
    no_tokens: int = sum(PS.values())
    for token in PS:
        PS[token] /= no_tokens
    log.info(f'finished generating word ps took {time() - start:4.2f} sec')
    return PS


def get_ngram_ps(n=2) -> Dict[Tuple, Dict[bytes, float]]:
    global NGRAM_PS

    assert n >= 1, f'ngram len must be >= 1 but got n = {n}'
    if NGRAM_PS is not None:
        log.info('got ngram ps from cache')
        return NGRAM_PS
    start = time()
    log.info('generating ngram ps')

    tokens: List[bytes] = get_tokens()

    NGRAM_PS = dict()

    for i in range(len(tokens) - n - 1):
        for m in range(1, n + 1):
            words_before: Tuple = tuple(tokens[i:i + m])
            next_word: bytes = tokens[i + m]
            if words_before not in NGRAM_PS:
                NGRAM_PS[words_before] = {next_word: 1}
            elif next_word in NGRAM_PS[words_before]:
                NGRAM_PS[words_before][next_word] += 1
            else:
                NGRAM_PS[words_before][next_word] = 1

    for ngram in NGRAM_PS:
        total = 0
        for count in NGRAM_PS[ngram].values():
            total += count
        if total > 0:
            for next_word in NGRAM_PS[ngram]:
                NGRAM_PS[ngram][next_word] /= total

    log.info(f'finished generating ngram ps (took {time() - start:4.2f} sec)')
    return NGRAM_PS


def root_path(*parts, mkparent=True, mkdir=False, mkfile=False) -> str:
    p: str = join(ROOT, *parts)
    if mkparent and not isdir(dirname(p)):
        makedirs(dirname(p))
    if mkdir and not isdir(p):
        makedirs(p)
    elif mkfile and not isfile(p):
        Path(p).touch()
    return p


def get_text(files=None, chunk_size_=10, quick=True) -> bytes:
    global TEXT
    if TEXT is not None:
        log.info('got text from cache')
        return TEXT
    start = time()
    if files is None:
        files = [join(ROOT, 'data', fname) for fname in listdir(join(ROOT, 'data'))]
    log.info(f'loading text from {len(files)} files {", ".join((basename(p) for p in files))}')
    chunk_size = chunk_size_
    chunks: List[bytes] = []
    for path in files:
        with open(path, mode='rb') as f:
            start_file = time()
            log.info(f'loading text from file "{path}"')
            while True:
                try:
                    c = f.read(chunk_size)
                    if not c:
                        break
                    else:
                        chunks.append(c)
                    chunk_size = min(chunk_size * 2, 100) if not quick else chunk_size * 2
                except Exception as e:
                    log.warning(str(e))
                    chunk_size = 10
        log.info(f'finished loading text from "{path}" (took {time() - start_file} sec)')
        chunks.append(b'\n\n')
    TEXT = b''.join(chunks)
    TEXT = CLEAN_REGEX.sub(b'', TEXT)
    TEXT = WRAP_REGEX.sub(rb'\1 \2', TEXT)
    TEXT = NL_REGEX.sub(b'\n\n', TEXT)
    log.info(f'finished loading text (took {time() - start:4.2f} sec)')
    return TEXT


def generate(txt=b'Harry was in a great mood that day.', n=6, max_avg_txt_len=(10000 * 8)) -> str:
    assert len(txt) // 3 >= n, \
        'Not enough text to generate a story (try adding more text).'
    start = time()
    tokens: List[bytes] = tokenize(txt)
    assert len(tokens) >= n, \
        f'Not enough text to generate a story ({len(tokens)} but need {n}).'
    succ = [0 for _ in range(n + 1)]
    ps: Dict[bytes, float] = get_ps()
    unique_tokens: List[bytes] = list(ps.keys())
    unique_tokens_ps: List[float] = list(ps.values())
    ps_ngrams = get_ngram_ps(n=n)

    # token generation
    while len(tokens) * 8 < max_avg_txt_len:
        found = False
        for m in range(n, 0, -1):
            ngram = tuple(tokens[-m:])
            maybe_ps: Optional[Dict[bytes, float]] = ps_ngrams.get(ngram, None)
            if maybe_ps and len(maybe_ps) > 1:
                succ[m] += 1
                tokens.append(choice(a=list(maybe_ps.keys()), p=list(maybe_ps.values())))
                found = True
                break
        if not found:
            succ[0] += 1
            tokens.append(choice(a=unique_tokens, p=unique_tokens_ps))

    # post-processing
    normalize(tokens=tokens, unique_tokens=unique_tokens)

    # metrics
    log.info('-' * 50)
    log.info('%s %12s %s' % ('NO', 'PROBABILITY', 'NO EXAMPLES'))
    log.info('%s %12s %s' % ('--', '-----------', '-----------'))
    no_gen_tokens: int = sum(succ)
    for i in range(n, -1, -1):
        log.info('%2d %12.10f (from %d examples)' % (i, succ[i] / no_gen_tokens, succ[i]))

    log.info(f'finished generating text (took {time() - start:4.2f} sec)')

    # text (outcome)
    return (b''.join(tokens) + b'.\n\nTHE END.').decode('ascii', 'ignore')

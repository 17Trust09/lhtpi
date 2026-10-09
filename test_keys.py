"""Test-Schlüssel für die Lizenzprüfung (kein echtes Geheimnis).

Beide Testsuiten (Lizenz, Router) signieren damit Lizenzen. Der **echte** private
Schlüssel liegt außerhalb des Repos und wird hier absichtlich nicht verwendet.
"""
import json
import os
import tempfile

TEST_KEY = {'n': 'e2c84b8ab499bad3e787f4967a8ebf76d496c97db6eceb19ec4c230e719a12810d89c933e5d58439ebea06cd1ebbb8fd688b4d724999972f83a37a9f4d03dadf90b36ecd33e976037ea7806b9581ea45c9a178f4f42269d0b9a128170f6f8d4a1ca2bbfdcb0c3ff59d861e0ff45f82c706750e778af995c7785435e7e1cbd043', 'e': 65537, 'd': '489dac1ab0f39cb027ae0ff27331ec3ae79d94cd2d5ab5792a81c2a3e85a565c7e72453bd9f7418cae6ed458afe39a3b825340ac3cc6f273236aa0640bec1513f09477653a55b697f4c6715b86685a8fcc40fc1f56ed76bc05c049f602d4237e0e8ee97409cd220f89bfcb9fb7d534ba7417e2df971d46d629fcc3218bcd5291'}


def install_env():
    """Umgebung so setzen, dass das Lizenzmodul mit dem Testschlüssel arbeitet."""
    ordner = tempfile.mkdtemp(prefix='lhtpi-testkey-')
    datei = os.path.join(ordner, 'privat.json')
    with open(datei, 'w') as f:
        json.dump(TEST_KEY, f)
    os.environ['LHTPI_SIGN_KEY_FILE'] = datei
    os.environ['LHTPI_PUBKEY'] = '%s:%d' % (TEST_KEY['n'], TEST_KEY['e'])
    return datei

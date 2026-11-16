"""Keeps the tests away from the settings of the user.

The tests read and write the settings of the app — the last project, the
list of the recent ones, the provider, the window geometry. They are
pointed at a directory of their own, so that a test that clears a
setting does not clear the setting of the user.

Every test file imports this before anything else.
"""

import tempfile

from PySide6.QtCore import QSettings

_DIRECTORY = tempfile.mkdtemp(prefix='taggui-test-settings-')
# The ini format keeps the settings in a plain file in that directory.
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
for _scope in (QSettings.Scope.UserScope, QSettings.Scope.SystemScope):
    QSettings.setPath(QSettings.Format.IniFormat, _scope, _DIRECTORY)

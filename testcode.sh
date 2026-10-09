#!/bin/bash
grep -rI "electrum\/" ../electrum-mona . 2> /dev/null | grep -v -e "\/locale\/" -e "README" -e "RELEASE-NOTES" -e "electrum\/{version\.ELECTRUM\_VERSION}" -e "\/issues\/" -e "\/pull\/5440"
grep -rI "import\ electrum " ../electrum-mona . 2> /dev/null | grep -v -e "\/locale\/" -e "README" -e "RELEASE-NOTES" -e "electrum\/{version\.ELECTRUM\_VERSION}" -e "\/issues\/" -e "\/pull\/5440"
grep -rI "import\ electrum\." ../electrum-mona . 2> /dev/null | grep -v -e "\/locale\/" -e "README" -e "RELEASE-NOTES" -e "electrum\/{version\.ELECTRUM\_VERSION}" -e "\/issues\/" -e "\/pull\/5440"
grep -rI "from\ electrum " ../electrum-mona . 2> /dev/null | grep -v -e "\/locale\/" -e "README" -e "RELEASE-NOTES" -e "electrum\/{version\.ELECTRUM\_VERSION}" -e "\/issues\/" -e "\/pull\/5440"
grep -rI "from\ electrum\." ../electrum-mona . 2> /dev/null | grep -v -e "\/locale\/" -e "README" -e "RELEASE-NOTES" -e "electrum\/{version\.ELECTRUM\_VERSION}" -e "\/issues\/" -e "\/pull\/5440"
grep -rI "electrum\.gui" ../electrum-mona . 2> /dev/null | grep -v -e "\/locale\/" -e "README" -e "RELEASE-NOTES" -e "electrum\/{version\.ELECTRUM\_VERSION}" -e "\/issues\/" -e "\/pull\/5440"
pytest tests/ --full-trace -vvvv
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

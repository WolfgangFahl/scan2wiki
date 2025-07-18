"""
Created on 2022-02-16

@author: wf
"""

from dataclasses import dataclass

import scan


@dataclass
class Version(object):
    """
    Version handling for scan2wiki
    """

    name = "scan2wiki"
    version = scan.__version__
    description = "Semantified Document Management System"
    date = "2021-12-20"
    updated = "2025-04-07"

    authors = "Wolfgang Fahl"

    doc_url = "https://wiki.bitplan.com/index.php/scan2wiki"
    chat_url = "https://github.com/WolfgangFahl/scan2wiki/discussions"
    cm_url = "https://github.com/WolfgangFahl/scan2wiki"

    license = f"""Copyright 2023-2025 contributors. All rights reserved.

  Licensed under the Apache License 2.0
  http://www.apache.org/licenses/LICENSE-2.0

  Distributed on an "AS IS" basis without warranties
  or conditions of any kind, either express or implied."""

    longDescription = f"""{name} version {version}
{description}

  Created by {authors} on {date} last updated {updated}"""

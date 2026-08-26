# scan2wiki
Scan from cams and scanners to Document Management System and SemanticMediaWiki

[![pypi](https://img.shields.io/pypi/pyversions/scan2wiki)](https://pypi.org/project/scan2wiki/)
[![Github Actions Build](https://github.com/WolfgangFahl/scan2wiki/actions/workflows/build.yml/badge.svg)](https://github.com/WolfgangFahl/scan2wiki/actions/workflows/build.yml)
[![PyPI Status](https://img.shields.io/pypi/v/scan2wiki.svg)](https://pypi.python.org/pypi/scan2wiki/)
[![GitHub issues](https://img.shields.io/github/issues/WolfgangFahl/scan2wiki.svg)](https://github.com/WolfgangFahl/scan2wiki/issues)
[![GitHub closed issues](https://img.shields.io/github/issues-closed/WolfgangFahl/scan2wiki.svg)](https://github.com/WolfgangFahl/scan2wiki/issues/?q=is%3Aissue+is%3Aclosed)
[![API Docs](https://img.shields.io/badge/API-Documentation-blue)](https://WolfgangFahl.github.io/scan2wiki/)
[![License](https://img.shields.io/github/license/WolfgangFahl/scan2wiki.svg)](https://www.apache.org/licenses/LICENSE-2.0)

[![BITPlan](http://wiki.bitplan.com/images/wiki/thumb/3/38/BITPlanLogoFontLessTransparent.png/198px-BITPlanLogoFontLessTransparent.png)](http://www.bitplan.com)


## Scan Interface
![scan2wiki scan interface with live view](docs/images/scan-interface.png)

## CLI Usage
### scan2wiki
Semantified Document Management System webserver

```bash
scan2wiki -h
```
```
usage: scan2wiki [-h] [-a] [-d] [--debugLocalPath DEBUGLOCALPATH]
                 [--debugPort DEBUGPORT] [--debugRemotePath DEBUGREMOTEPATH]
                 [--debugServer DEBUGSERVER] [-f] [-q] [-v] [-V]
                 [--apache APACHE] [-c] [-l] [-i INPUT] [-rol] [--host HOST]
                 [--port PORT] [-s] [-rp ROOT_PATH] [-wc WEBCAMS]
                 [--web-host WEB_HOST]
```
Start the webserver on the default port 8334:
```bash
scan2wiki -s
```
Serve with webcams configured as name-url pairs:
```bash
scan2wiki -s --webcams cam1=http://cam1.example/mjpeg
```

### cam2web
The webcam emulator serving a gphoto2 camera moved to its own project, see
[cam2web](https://github.com/WolfgangFahl/cam2web).

## Links
* [Python](https://www.python.org/)
* [pywikibot](https://pypi.org/project/pywikibot/)
* [scan2wiki on pypi](https://pypi.org/project/scan2wiki)

## Documentation
[Wiki](http://wiki.bitplan.com/index.php/scan2wiki)

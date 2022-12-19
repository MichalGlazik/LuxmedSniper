# LuxmedSniper
LUX MED appointments sniper
=======================================
Simple tool to notify about available slot in LUX MED medical care service using pushover notifications.

How to use LuxmedSniper?
--------------------
Build it with Docker

`docker build -t luxmed-sniper .`

# Warning

Please be advised that running too many queries against LuxMed API may result in locking your LuxMed account.
Breaching the 'fair use policy' for the first time locks the account temporarily for 1 day.
Breaching it again locks it indefinitelly and manual intervention with "Patient Portal Support" is required to unlock it.

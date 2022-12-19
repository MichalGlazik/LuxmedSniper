import argparse
import firebase_admin
from firebase_admin import credentials, firestore
import envyaml
import json
import logging
import os
import datetime
import requests

log = logging.getLogger()

class LuxMedSniper:
    LUXMED_LOGIN_URL = 'https://portalpacjenta.luxmed.pl/PatientPortalMobileAPI/api/token'
    NEW_PORTAL_RESERVATION_URL = 'https://portalpacjenta.luxmed.pl/PatientPortalMobileAPI/api/visits/available-terms'

    def __init__(self, configuration_file="luxmedSniper.yaml"):
        self.log = logging.getLogger()
        self.log.info("LuxMedSniper logger initialized")
        self._loadConfiguration(configuration_file)
        self._createSession()
        self._logIn()
        self._load_appointments()

    def _load_appointments(self):
        cred = credentials.Certificate(
            self.config['firebase']['firebase_key']
        )
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        self.seen_appointments_ref = db.document('luxmed-sniper', 'seen-appointments')
        seen_appointments = self.seen_appointments_ref.get().to_dict()
        if not seen_appointments:
            seen_appointments = {}
        self.seen_appointments = seen_appointments

    def _createSession(self):
        self.session = requests.session()
        self.session.headers.update({
            'Custom-User-Agent': 'PatientPortal; 4.14.0; 4380E6AC-D291-4895-8B1B-F774C318BD7D; iOS; 13.5.1; iPhone8,1'})
        self.session.headers.update({
            'User-Agent': 'PatientPortal/4.14.0 (pl.luxmed.pp.LUX-MED; build:853; iOS 13.5.1) Alamofire/4.9.1'})
        self.session.headers.update({'Accept-Language': 'en;q=1.0, en-PL;q=0.9, pl-PL;q=0.8, ru-PL;q=0.7, uk-PL;q=0.6'})
        self.session.headers.update({'Accept-Encoding': 'gzip;q=1.0, compress;q=0.5'})

    def _loadConfiguration(self, configuration_file):
        try:
            config_data_path = os.path.expanduser(configuration_file)
        except IOError:
            raise Exception('Cannot open configuration file ({file})!'.format(file=configuration_file))
        try:
            self.config = envyaml.EnvYAML(config_data_path)
        except Exception as yaml_error:
            raise Exception('Configuration problem: {error}'.format(error=yaml_error))

    def _logIn(self):
        login_data = {'grant_type': 'password', 'client_id': 'iPhone', 'username': self.config['luxmed']['email'],
                      'password': self.config['luxmed']['password']}
        resp = self.session.post(self.LUXMED_LOGIN_URL, login_data)
        content = json.loads(resp.text)
        self.access_token = content['access_token']
        self.refresh_token = content['refresh_token']
        self.token_type = content['token_type']
        self.session.headers.update({'Authorization': '%s %s' % (self.token_type, self.access_token)})
        self.log.info('Successfully logged in!')

    def _parseVisitsNewPortal(self, data):
        appointments = []
        content = json.loads(data)
        for term in content['AvailableVisitsTermPresentation']:
            appointments.append(
                {'AppointmentDate': '%s' % term['VisitDate']['FormattedDate'],
                 'ClinicPublicName': term['Clinic']['Name'],
                 'DoctorName': '%s' % term['Doctor']['Name']})
        return appointments

    def _getAppointmentsNewPortal(self):
        try:
            (cityId, serviceId, clinicId, doctorId) = self.config['luxmedsniper'][
                'doctor_locator_id'].strip().split('*')
        except ValueError:
            raise Exception('DoctorLocatorID seems to be in invalid format')
        data = {
            'cityId': cityId,
            'payerId': 123,
            'serviceId': serviceId,
            'languageId': 10,
            'FromDate': datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            'ToDate': (datetime.datetime.now() + datetime.timedelta(
                days=self.config['luxmedsniper']['lookup_time_days'])).strftime("%Y-%m-%dT%H:%M:%SZ"),
            'searchDatePreset': self.config['luxmedsniper']['lookup_time_days']
        }
        if clinicId != '-1':
            data['clinicId'] = clinicId
        if doctorId != '-1':
            data['doctorId'] = doctorId

        r = self.session.get(self.NEW_PORTAL_RESERVATION_URL, params=data)
        return self._parseVisitsNewPortal(r.text)

    def check(self):
        appointments = self._getAppointmentsNewPortal()
        if not appointments:
            self.log.info("No appointments found.")
            return
        for appointment in appointments:
            self.log.info(
                "Appointment found! {AppointmentDate} at {ClinicPublicName} - {DoctorName}".format(
                    **appointment))
            if not self._isAlreadyKnown(appointment):
                self._addToDatabase(appointment)
                self._sendNotification(appointment)
                self.log.info(
                    "Notification sent! {AppointmentDate} at {ClinicPublicName} - {DoctorName}".format(
                        **appointment))
            else:
                self.log.info('Notification was already sent.')

    def _addToDatabase(self, appointment):
        doctor_name = appointment['DoctorName']
        appointment_date = appointment['AppointmentDate']
        seen_dates = self.seen_appointments.get(doctor_name, [])
        seen_dates.append(appointment_date)
        update_ = {doctor_name: seen_dates}
        self.seen_appointments.update(update_)
        self.seen_appointments_ref.set(update_, merge=True)

    def _sendNotification(self, appointment):
        try:
            requests.post(
                'https://api.pushover.net/1/messages.json',
                data={
                    'message': self.config['pushover']['message_template'].format(
                        **appointment, title=self.config['pushover']['title']),
                    'user': self.config['pushover']['user_key'],
                    'token': self.config['pushover']['api_token']
                }
            )
        except Exception as s:
            log.error(s)

    def _isAlreadyKnown(self, appointment):
        notifications = self.seen_appointments.get(appointment['DoctorName'], [])
        if appointment['AppointmentDate'] in notifications:
            return True
        return False


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c", "--config",
        help="Configuration file path (default: luxmedSniper.yaml)", default="luxmedSniper.yaml"
    )
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    log.info("LuxMedSniper - Lux Med Appointment Sniper")
    args = parse_args()
    LuxMedSniper(configuration_file=args.config).check()



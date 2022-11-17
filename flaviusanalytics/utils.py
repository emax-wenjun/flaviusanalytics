from twilio.rest import Client

client = Client("ACafad00dd859a82eb7d1b011d272dd4c4", "2f6a3c5eefd3edb2d332e1ca68674638")

def send_text(body):
    client.messages.create(body = body, from_ = "+14793395115", to = "+15039060652")
enum Etat { IDLE, RUNNING, ERROR };

Etat etat = IDLE;

void loop() {
    switch (etat) {
        case IDLE:
            if (bouton) etat = RUNNING;
            break;
        case RUNNING:
            if (erreur) etat = ERROR;
            if (stop) etat = IDLE;
            break;
        case ERROR:
            if (reset) etat = IDLE;
            break;
    }
}
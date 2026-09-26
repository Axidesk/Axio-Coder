const ouvintes = new Set();
let mostrando = false;

export function mostrandoOcultos() {
    return mostrando;
}

export function aoMudarOcultos(ouvinte) {
    ouvintes.add(ouvinte);
    return function () {
        ouvintes.delete(ouvinte);
    };
}

export function alternarOcultos() {
    mostrando = !mostrando;
    ouvintes.forEach(function (ouvinte) {
        ouvinte(mostrando);
    });
    return mostrando;
}

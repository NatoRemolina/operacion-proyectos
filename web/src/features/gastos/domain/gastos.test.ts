import { describe, expect, it } from "vitest";
import { validarArchivo } from "./gastos";

describe("archivo del recibo", () => {
  it("el tope es el mismo que el del servidor (4,5 MB, no 4,5 MiB)", () => {
    expect(validarArchivo({ size: 4_500_000, type: "image/jpeg", name: "recibo.jpg" })).toBeNull();
    expect(validarArchivo({ size: 4_600_000, type: "image/jpeg", name: "recibo.jpg" })).toBe("demasiado_grande");
  });

  it("acepta el correo de una reserva (.eml) aunque el navegador no le ponga tipo o le ponga uno genérico", () => {
    for (const type of ["message/rfc822", "", "application/octet-stream"]) {
      expect(validarArchivo({ size: 2_000, type, name: "correo_tiquete.eml" }), type).toBeNull();
    }
    expect(validarArchivo({ size: 2_000, type: "text/html", name: "pagina.html" })).toBe("tipo_no_admitido");
    expect(validarArchivo({ size: 2_000, type: "application/octet-stream", name: "programa.exe" })).toBe("tipo_no_admitido");
  });
});

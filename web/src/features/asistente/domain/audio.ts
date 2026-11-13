/**
 * La voz viaja como WAV PCM de 16 bits, mono, a 16 kHz: un formato que el servicio que transcribe acepta
 * siempre, venga la grabación de Chrome (WebM), Safari (MP4) o Firefox (Ogg). Un minuto pesa unos 1,9 MB.
 */
export const FRECUENCIA_VOZ = 16_000;

export function codificarWav(muestras: Float32Array, frecuencia: number = FRECUENCIA_VOZ): ArrayBuffer {
  const bytesDatos = muestras.length * 2;
  const buffer = new ArrayBuffer(44 + bytesDatos);
  const vista = new DataView(buffer);
  const texto = (desde: number, valor: string) => {
    for (let i = 0; i < valor.length; i++) vista.setUint8(desde + i, valor.charCodeAt(i));
  };
  texto(0, "RIFF");
  vista.setUint32(4, 36 + bytesDatos, true);
  texto(8, "WAVE");
  texto(12, "fmt ");
  vista.setUint32(16, 16, true); // tamaño del bloque fmt
  vista.setUint16(20, 1, true); // PCM
  vista.setUint16(22, 1, true); // mono
  vista.setUint32(24, frecuencia, true);
  vista.setUint32(28, frecuencia * 2, true); // bytes por segundo
  vista.setUint16(32, 2, true); // bytes por muestra
  vista.setUint16(34, 16, true); // bits por muestra
  texto(36, "data");
  vista.setUint32(40, bytesDatos, true);
  for (let i = 0; i < muestras.length; i++) {
    const s = Math.max(-1, Math.min(1, muestras[i] ?? 0));
    vista.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

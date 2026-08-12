/** Rotates the uploaded file and not the element on screen: the ROI
 *  rectangles are pixels of the image the worker receives. Always from the
 *  original file, so four quarter turns land where they started. */
export async function rotate(file, degrees) {
  if (degrees % 360 === 0) return file;

  const bitmap = await createImageBitmap(file);
  const quarter = degrees % 180 !== 0;
  const canvas = document.createElement("canvas");
  canvas.width = quarter ? bitmap.height : bitmap.width;
  canvas.height = quarter ? bitmap.width : bitmap.height;

  const context = canvas.getContext("2d");
  context.translate(canvas.width / 2, canvas.height / 2);
  context.rotate((degrees * Math.PI) / 180);
  context.drawImage(bitmap, -bitmap.width / 2, -bitmap.height / 2);
  bitmap.close();

  const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
  // PNG and not JPEG: a lossy codec would move the pixel values the
  // threshold is set against.
  return new File([blob], `${file.name.replace(/\.[^.]+$/, "")}.png`, { type: "image/png" });
}

/** Mean and standard deviation per channel. Local to the tab. */
export async function colourStatistics(file, roi) {
  const bitmap = await createImageBitmap(file);
  const box = roi ?? { x: 0, y: 0, width: bitmap.width, height: bitmap.height };

  const canvas = document.createElement("canvas");
  canvas.width = box.width;
  canvas.height = box.height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(bitmap, box.x, box.y, box.width, box.height, 0, 0, box.width, box.height);
  bitmap.close();

  const { data } = context.getImageData(0, 0, box.width, box.height);
  const pixels = data.length / 4;
  const sum = [0, 0, 0];
  const squares = [0, 0, 0];
  for (let index = 0; index < data.length; index += 4) {
    for (let channel = 0; channel < 3; channel += 1) {
      const value = data[index + channel];
      sum[channel] += value;
      squares[channel] += value * value;
    }
  }

  const mean = sum.map((total) => total / pixels);
  // Clamped at zero: the sum-of-squares form can land a hair below it on a
  // uniform region, and NaN would reach the screen.
  const sd = squares.map((total, channel) =>
    Math.sqrt(Math.max(total / pixels - mean[channel] ** 2, 0)),
  );
  return { mean, sd };
}

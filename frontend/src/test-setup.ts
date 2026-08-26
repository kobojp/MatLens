import "@testing-library/jest-dom/vitest";

Object.defineProperty(URL, "createObjectURL", {
  configurable: true,
  value: (file: File) => `blob:matlens/${file.name}`,
});

Object.defineProperty(URL, "revokeObjectURL", {
  configurable: true,
  value: () => undefined,
});

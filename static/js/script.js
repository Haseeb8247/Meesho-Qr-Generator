document.addEventListener("DOMContentLoaded", () => {
  const pdfInput = document.getElementById("pdf_file");
  const csvInput = document.getElementById("csv_file");
  const pdfName = document.getElementById("pdfName");
  const csvName = document.getElementById("csvName");
  const form = document.getElementById("uploadForm");
  const button = document.getElementById("generateButton");
  const buttonText = document.getElementById("buttonText");
  const buttonArrow = document.getElementById("buttonArrow");
  const loadingMessage = document.getElementById("loadingMessage");

  if (!form) return;

  pdfInput.addEventListener("change", () => {
    pdfName.textContent = pdfInput.files.length ? pdfInput.files[0].name : "No file selected";
  });
  csvInput.addEventListener("change", () => {
    csvName.textContent = csvInput.files.length ? csvInput.files[0].name : "No file selected";
  });

  form.addEventListener("submit", (event) => {
    if (!pdfInput.files.length || !csvInput.files.length) {
      event.preventDefault();
      alert("Please select both the PDF and CSV files.");
      return;
    }
    if (!pdfInput.files[0].name.toLowerCase().endsWith(".pdf")) {
      event.preventDefault(); alert("Please select a PDF shipping-label file."); return;
    }
    if (!csvInput.files[0].name.toLowerCase().endsWith(".csv")) {
      event.preventDefault(); alert("Please select an orders CSV file."); return;
    }
    button.disabled = true;
    buttonText.textContent = "Processing orders...";
    buttonArrow.hidden = true;
    loadingMessage.hidden = false;
  });
});

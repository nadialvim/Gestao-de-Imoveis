(function () {
  // Menu lateral no celular/tablet
  var body = document.body;
  document.querySelectorAll("[data-menu-toggle]").forEach(function (el) {
    el.addEventListener("click", function () { body.classList.toggle("menu-open"); });
  });

  // Modal de baixa de contrato
  var modalBaixa = document.getElementById("modalBaixa");
  if (modalBaixa) {
    modalBaixa.addEventListener("show.bs.modal", function (ev) {
      var b = ev.relatedTarget;
      document.getElementById("formBaixa").setAttribute("action", b.getAttribute("data-action"));
      document.getElementById("baixaNome").textContent = b.getAttribute("data-nome");
    });
  }

  // Busca nas tabelas
  var input = document.getElementById("busca");
  if (input) {
    var linhas = document.querySelectorAll("table[data-busca] tbody tr[data-row]");
    var contador = document.getElementById("contador");
    var vazio = document.getElementById("sem-resultado");
    var norm = function (s) {
      return s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
    };
    input.addEventListener("input", function () {
      var q = norm(input.value.trim()), n = 0;
      linhas.forEach(function (tr) {
        var ok = !q || norm(tr.textContent).indexOf(q) !== -1;
        tr.style.display = ok ? "" : "none";
        if (ok) n++;
      });
      if (contador) contador.textContent = n;
      if (vazio) vazio.style.display = n === 0 && linhas.length ? "" : "none";
    });
  }

  // Gráfico do dashboard
  var canvas = document.getElementById("grafico-meses");
  if (canvas && window.Chart) {
    var dados = JSON.parse(canvas.getAttribute("data-serie"));
    var brl = function (v) {
      return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
    };
    new Chart(canvas, {
      type: "bar",
      data: {
        labels: dados.map(function (d) { return d.rotulo; }),
        datasets: [
          { label: "Recebido", data: dados.map(function (d) { return d.recebido; }),
            backgroundColor: "#0e7490", borderRadius: 6 },
          { label: "Despesas", data: dados.map(function (d) { return d.despesas; }),
            backgroundColor: "#e08a7d", borderRadius: 6 }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom" },
          tooltip: { callbacks: { label: function (c) { return c.dataset.label + ": " + brl(c.parsed.y); } } }
        },
        scales: {
          y: { beginAtZero: true, ticks: { callback: function (v) { return brl(v); } }, grid: { color: "#eef2f4" } },
          x: { grid: { display: false } }
        }
      }
    });
  }
})();

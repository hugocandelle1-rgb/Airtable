#include "atcore/tach.h"

namespace atc {

void TachEstimator::configure(float ppr, uint32_t window_us, uint32_t timeout_us) {
  ppr_ = ppr > 0.0f ? ppr : 2.0f;
  window_us_ = window_us;
  timeout_us_ = timeout_us;
  reset();
}

void TachEstimator::reset() { n_ = 0; head_ = 0; rpm_ = 0.0f; have_last_ = false; }

void TachEstimator::sample(uint32_t now_us, uint32_t count, uint32_t last_edge_us) {
  if (!have_last_) { last_count_ = count; have_last_ = true; }
  // Aucun front récent : arrêt (ou fil coupé).
  if (count == last_count_ && static_cast<uint32_t>(now_us - last_edge_us) > timeout_us_) {
    rpm_ = 0.0f;
    n_ = 0;
    return;
  }
  last_count_ = count;
  // On n'archive qu'un échantillon par valeur distincte du compteur.
  const bool is_new = (n_ == 0) || (ring_[(head_ + kRing - 1) % kRing].count != count);
  if (is_new) {
    ring_[head_] = {count, last_edge_us};
    head_ = (head_ + 1) % kRing;
    if (n_ < kRing) ++n_;
  }
  if (n_ < 2) return;
  const Entry newest = ring_[(head_ + kRing - 1) % kRing];
  // Référence : l'entrée la plus récente distante d'au moins window_us, sinon la plus ancienne.
  Entry ref = ring_[(head_ + kRing - n_) % kRing];
  for (int k = 2; k <= n_; ++k) {
    const Entry& e = ring_[(head_ + kRing - k) % kRing];
    if (static_cast<uint32_t>(newest.t_us - e.t_us) >= window_us_) { ref = e; break; }
  }
  const uint32_t dt = static_cast<uint32_t>(newest.t_us - ref.t_us);
  const uint32_t dc = newest.count - ref.count;
  if (dt == 0 || dc == 0) return;
  rpm_ = 60.0e6f * static_cast<float>(dc) / (ppr_ * static_cast<float>(dt));
}

}  // namespace atc

# Báo Cáo Cá Nhân — Lab Day 08: RAG Pipeline

**Họ và tên:** Jin  
**Vai trò trong nhóm:** Documentation Owner (phối hợp Evaluation)  
**Ngày nộp:** 2026-04-13

## 1. Tôi đã làm gì trong lab này?

Trong lab này, tôi tập trung chính vào phần tài liệu kỹ thuật và tổng hợp kết quả thử nghiệm để nhóm có thể nộp đúng rubric. Tôi phụ trách cập nhật kiến trúc pipeline trong `docs/architecture.md`, bao gồm mô tả luồng index -> retrieval -> generation, các quyết định chunking, metadata và cấu hình baseline/variant. Song song đó, tôi tổng hợp kết quả A/B vào `docs/tuning-log.md` và chuyển các số liệu quan trọng sang scorecard markdown trong thư mục `results/`.

Công việc của tôi kết nối trực tiếp với phần code của Tech Lead/Retrieval Owner: khi pipeline thay đổi từ dense sang hybrid, tôi cập nhật lại rationale và bảng so sánh để đảm bảo tài liệu phản ánh đúng hành vi hệ thống. Ngoài ra, tôi chuẩn hóa nhóm file nộp (`logs/`, `reports/`) để tránh mất điểm vì thiếu deliverable dù code đã chạy.

## 2. Điều tôi hiểu rõ hơn sau lab này

Điều tôi hiểu rõ nhất sau lab là retrieval thường quyết định chất lượng cuối cùng của RAG nhiều hơn phần generation. Trước đây tôi nghĩ chỉ cần prompt tốt là đủ, nhưng khi xem kết quả baseline dense, mình thấy model vẫn có thể trả lời lệch nếu chunk retrieve chưa đúng trọng tâm. Khi chuyển sang hybrid (dense + BM25), độ bám câu hỏi tăng vì BM25 giữ lại tín hiệu keyword quan trọng, còn dense giữ ngữ nghĩa tổng quát.

Khái niệm thứ hai là tầm quan trọng của vòng lặp evaluation. Nếu chỉ đọc vài output mẫu thì rất dễ thiên kiến. Dùng scorecard với các trục faithfulness/relevance/recall/completeness giúp nhóm nhìn rõ mình đang yếu ở stage nào, thay vì sửa ngẫu nhiên.

## 3. Điều tôi ngạc nhiên hoặc gặp khó khăn

Khó khăn lớn nhất là có những câu hỏi nhìn rất đơn giản nhưng pipeline vẫn trượt vì semantic noise: chunk được retrieve có vẻ "liên quan", nhưng khác phòng ban hoặc khác ngữ cảnh thời gian. Điều này làm model trả lời có vẻ hợp lý nhưng không đúng tài liệu cần thiết. Lúc đầu tôi nghĩ lỗi nằm ở prompt vì model trả lời dài và đôi lúc suy diễn, nhưng khi đối chiếu context thì nguyên nhân gốc lại đến từ retrieval.

Tôi cũng bất ngờ về yêu cầu nộp bài: không chỉ code chạy, mà bằng chứng file nộp đúng cấu trúc và đúng deadline cũng ảnh hưởng lớn đến điểm. Vì vậy phần tài liệu và log không thể làm sau cùng một cách qua loa; nếu thiếu file bắt buộc thì mất điểm dù pipeline tương đối tốt.

## 4. Phân tích một câu hỏi trong scorecard

**Câu hỏi:** q09 (Insufficient Context)

Ở baseline dense, q09 có điểm rất thấp vì hệ thống chưa từ chối đủ mạnh trong tình huống context không đủ. Về mặt triệu chứng, answer vẫn cố đưa ra một kết luận "an toàn", nhưng không có bằng chứng trực tiếp từ chunk retrieve. Đây là failure mode điển hình giữa retrieval và generation: retriever không đưa về bằng chứng đủ chắc, còn generator không thực thi abstain đủ nghiêm.

Khi chuyển sang variant hybrid, phần retrieval cải thiện theo hướng lọc keyword tốt hơn nên giảm nhiễu ở một số câu, nhưng với nhóm câu "insufficient context" thì vẫn cần kết hợp thêm rule ở generation (ví dụ yêu cầu nêu rõ "không đủ dữ liệu trong tài liệu hiện có"). Tức là hybrid giúp tăng precision chung, nhưng không tự động giải quyết hoàn toàn bài toán abstain.

Nếu trace theo error tree, root cause chính là thiếu evidence retrieval cho câu hỏi này; root cause phụ là prompt chưa ép cơ chế từ chối đủ mạnh khi evidence yếu. Fix phù hợp là thêm điều kiện confidence/coverage threshold trước khi trả lời cuối cùng, hoặc thêm hậu kiểm faithfulness để chặn câu trả lời không có chứng cứ rõ.

## 5. Nếu có thêm thời gian, tôi sẽ làm gì?

Nếu có thêm thời gian, tôi sẽ thử query transformation theo alias expansion (ví dụ mở rộng viết tắt SLA, approval terms) trước bước retrieve để tăng recall cho các câu hỏi ngắn. Tôi cũng muốn thêm một lớp abstain gate đơn giản: nếu top chunk score thấp hoặc context không chứa thực thể chính của câu hỏi thì trả về "không đủ dữ liệu". Hai cải tiến này bám trực tiếp vào điểm yếu đã thấy trong scorecard (đặc biệt nhóm câu thiếu ngữ cảnh).
